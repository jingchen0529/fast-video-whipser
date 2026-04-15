import logging
import json
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

from app.http_client import AsyncHttpClient
from app.services.system_settings_service import SystemSettingsService


DEFAULT_DOUBAO_ENDPOINT_ID = "a604da88-88a8-4760-bd6a-015eff016604"
DEFAULT_DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_DOUBAO_MODEL_NAME = "doubao-seed-1-6-250615"


class AnalysisAIService:
    async def generate_motion_tags_reply(
        self,
        *,
        source_name: str,
        candidate: dict[str, Any],
        fallback_payload: dict[str, Any],
        extraction_hint: str | None = None,
        provider_group: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        system_prompt = (
            "你是一名短视频动作资产标注专家，擅长把镜头片段整理成结构化动作标签。"
            "请根据镜头描述、转写文本、运镜和景别，输出严格 JSON。"
            "如果信息不足，请保守判断，不要编造具体人物身份。"
            "如果给了提取偏好，也只能在片段证据支持时作为优先参考，不能仅凭偏好臆断。"
            "除了常见人物动作，也要识别工业展示与产品展示场景。"
            "对于工厂/产品类视频，优先考虑以下动作标签："
            "team_greeting、operate_machine、carry_goods、display_product、inspect_product、"
            "material_flow、pour_material、package_product。"
            "对于工厂/产品类视频，优先考虑以下场景标签："
            "factory_entrance、factory_workshop、production_line、warehouse、machine_station、"
            "product_closeup、factory_exterior、loading_area。"
            "禁止输出任意自由组合标签，例如“smile, wave”或“factory entrance”；"
            "必须输出单个规范化标签，如 team_greeting 或 factory_entrance。"
        )
        user_prompt = "\n".join(
            [
                *(
                    [f"本次提取偏好（仅作辅助参考，不能覆盖片段事实）：{extraction_hint.strip()}"]
                    if extraction_hint and extraction_hint.strip()
                    else []
                ),
                f"素材名称：{source_name}",
                f"片段信息：{candidate}",
                (
                    "请只输出 JSON，字段必须包含："
                    '{"action_label":"","entrance_style":"","emotion_label":"","temperament_label":"",'
                    '"scene_label":"","camera_motion":"","camera_shot":"","action_summary":"",'
                    '"confidence":0.0,"is_high_value":true}'
                ),
                "其中：camera_motion 使用 static/pan/tilt/tracking/push_in/pull_out/zoom_in/zoom_out/handheld/mixed，"
                "camera_shot 使用 wide/full/medium/medium_close/close_up/extreme_close_up/mixed。",
            ]
        )
        return await self._complete_payload_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_payload=fallback_payload,
            provider_group=provider_group,
        )

    async def generate_analysis_reply(
        self,
        *,
        objective: str,
        source_name: str,
        source_analysis: dict[str, Any],
        timeline_segments: list[dict[str, Any]],
        script_overview: dict[str, Any],
        storyboard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        system_prompt = (
            "你是一名资深的 TikTok 电商短视频策略分析师，擅长拆解具有极高转化率的商业爆款视频。"
            "你的分析应深入挖掘视频如何通过钩子（Hook）、视觉节奏、脚本结构和转化机制实现转化。"
            "\n要求："
            "1. 爆点总结：一句话点出视频的核心优势。"
            "2. 开头钩子：精准分析前 3 秒如何留人（如：价格震撼、视觉反差、人设吸引）。"
            "3. 画面与节奏：分析运镜风格、剪辑点与音乐如何配合展示产品。"
            "4. 脚本结构：将口播/字幕拆解为逻辑段落（如：抛出问题 -> 解决方案 -> 价格优势 -> 信任背书）。"
            "5. 转化动作：详细描述结尾如何引导用户联系、购买或留言。"
            "\n输出 Markdown 格式，层级清晰，表达专业。"
        )
        user_prompt = "\n".join(
            [
                f"分析目标：{objective or '请拆解该视频的爆款基因和脚本结构'}",
                f"素材名称：{source_name}",
                f"画面特征（含视觉提取结果）：{source_analysis}",
                f"分镜详情（含视觉动作描述）：{storyboard or {'summary': '', 'items': []}}",
                f"脚本片段（ASR/OCR 结果）：{timeline_segments}",
                f"脚本全文：{script_overview.get('full_text', '')}",
                "请输出以下结构的深度分析：\n"
                "## 爆点总结\n"
                "## 开头钩子分析\n"
                "## 画面与节奏分析\n"
                "## 脚本结构分析\n"
                "## 转化动作分析\n",
            ]
        )
        fallback_content = self._build_fallback_analysis(
            objective=objective,
            source_name=source_name,
            source_analysis=source_analysis,
            timeline_segments=timeline_segments,
            script_overview=script_overview,
            storyboard=storyboard,
        )
        return await self._complete_markdown(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_content=fallback_content,
        )

    async def generate_storyboard_reply(
        self,
        *,
        objective: str,
        source_name: str,
        video_meta: dict[str, Any],
        shot_segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system_prompt = (
            "你是一名资深的短视频导演和分镜整理师，擅长将零散的镜头素材整理成具有高度叙事感和导购逻辑的分镜脚本。"
            "你的目标是生成极其详尽、专业、符合 TikTok 电商爆款节奏的分镜 JSON。"
            "\n要求："
            "1. 颗粒度：不要简单堆砌原始片段。如果一个片段过长或包含多个关键视觉变化，请在逻辑上拆分为多个分镜（items）。"
            "2. 视觉描述：必须包含人物、动作、服装、背景环境和关键道具的细节（例如：'一位身穿白色短袖的东亚女性在机床前随着节奏舞动'）。"
            "3. 镜头语言：准确识别全景(wide)、中景(medium)、特写(close_up)等景别，以及平视(eye_level)、俯视(top_view)等角度。"
            "4. 商业重点：在视觉描述中突出价格标签、型号展示、联系方式等转化关键点。"
            "\n输出必须是 JSON 对象，且只返回 JSON，不要附加解释。"
        )
        user_prompt = "\n".join(
            [
                f"分析目标：{objective or '整理视频分镜，突出爆点和产品卖点'}",
                f"素材名称：{source_name}",
                f"视频元信息：{video_meta}",
                f"输入镜头段（含脚本内容）：{shot_segments}",
                (
                    "请输出符合以下示例结构的 JSON："
                    '{"summary":"...", "items":[{"item_index":1,"title":"开场引入","start_ms":0,"end_ms":5800,'
                    '"shot_type_code":"wide","camera_angle_code":"eye_level","camera_motion_code":"static",'
                    '"visual_description":"展示VMC1050 CNC机床，屏幕出现价格$22,000，背景为整洁的工厂车间。","source_segment_indexes":[1],"confidence":0.9}]}.'
                ),
            ]
        )
        fallback_storyboard = self._build_fallback_storyboard(
            objective=objective,
            source_name=source_name,
            shot_segments=shot_segments,
        )
        return await self._complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_payload=fallback_storyboard,
        )

    async def generate_suggestions_reply(
        self,
        *,
        objective: str,
        source_name: str,
        analysis_content: str,
    ) -> dict[str, Any]:
        system_prompt = (
            "你是一名 TikTok 电商投放优化顾问。"
            "请根据已有分析输出 5 条强执行性的优化建议，每条建议都要写清问题、动作和预期收益。"
        )
        user_prompt = "\n".join(
            [
                f"分析目标：{objective or '优化短视频脚本与转化'}",
                f"素材名称：{source_name}",
                "已有分析内容如下：",
                analysis_content,
                "请直接输出 5 条编号建议。",
            ]
        )
        fallback_content = self._build_fallback_suggestions(
            objective=objective,
            source_name=source_name,
        )
        return await self._complete_markdown(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_content=fallback_content,
        )

    async def generate_chat_reply(
        self,
        *,
        messages: list[dict[str, str]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = (
            "你是一名专业的视频内容分析专家。根据提供的视频分析上下文，回答用户的问题。"
            "尽量简洁、专业，并结合视频内容（脚本、画面特征等）给出具体建议。"
        )
        # Convert internal history format if needed
        # Or just use the messages as is if they match OpenAI format
        
        provider = self._resolve_provider()
        api_key = provider.get("api_key") or ""
        base_url = provider.get("base_url") or ""
        request_model = provider.get("request_model") or ""

        if not api_key or not base_url or not request_model:
            return {
                "content": "抱歉，当前 AI 模型配置不完整，无法回复。但是您可以继续查看已有的分析结果。",
                "provider": provider.get("provider", "doubao"),
                "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                "used_remote": False,
            }

        payload_messages = [{"role": "system", "content": f"{system_prompt}\n上下文：{context}"}]
        payload_messages.extend(messages)

        payload = {
            "model": request_model,
            "temperature": 0.5,
            "messages": payload_messages,
        }

        try:
            async with AsyncHttpClient(
                follow_redirects=True,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                request_timeout=60,
            ) as client:
                response = await client.fetch_post_json(
                    self._build_chat_completions_url(base_url),
                    json=payload,
                )
            content = self._extract_message_content(response)
            if content:
                return {
                    "content": content,
                    "provider": provider.get("provider", "doubao"),
                    "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                    "used_remote": True,
                }
        except Exception as exc:
            logger.exception("Chat reply failed: provider=%s model=%s url=%s", provider.get("provider"), request_model, base_url)
            error_detail = str(exc).strip() or "未知错误"
            return {
                "content": f"抱歉，回复生成失败：{error_detail}",
                "provider": provider.get("provider", "doubao"),
                "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                "used_remote": False,
            }

    async def _complete_markdown(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback_content: str,
    ) -> dict[str, Any]:
        provider = self._resolve_provider()
        api_key = provider.get("api_key") or ""
        base_url = provider.get("base_url") or ""
        request_model = provider.get("request_model") or ""

        if not api_key or not base_url or not request_model:
            return {
                "content": fallback_content,
                "provider": provider.get("provider", "doubao"),
                "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                "used_remote": False,
            }

        payload = {
            "model": request_model,
            "temperature": 0.4,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        try:
            async with AsyncHttpClient(
                follow_redirects=True,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                request_timeout=60,
            ) as client:
                response = await client.fetch_post_json(
                    self._build_chat_completions_url(base_url),
                    json=payload,
                )
            content = self._extract_message_content(response)
            if content:
                return {
                    "content": content,
                    "provider": provider.get("provider", "doubao"),
                    "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                    "used_remote": True,
                }
        except Exception:
            pass

        return {
            "content": fallback_content,
            "provider": provider.get("provider", "doubao"),
            "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
            "used_remote": False,
        }

    async def _complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        provider = self._resolve_provider()
        api_key = provider.get("api_key") or ""
        base_url = provider.get("base_url") or ""
        request_model = provider.get("request_model") or ""

        if not api_key or not base_url or not request_model:
            return {
                "storyboard": fallback_payload,
                "provider": provider.get("provider", "doubao"),
                "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                "used_remote": False,
            }

        payload = {
            "model": request_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        try:
            async with AsyncHttpClient(
                follow_redirects=True,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                request_timeout=60,
            ) as client:
                response = await client.fetch_post_json(
                    self._build_chat_completions_url(base_url),
                    json=payload,
                )
            content = self._extract_message_content(response)
            parsed_payload = self._extract_json_payload(content)
            if parsed_payload:
                return {
                    "storyboard": parsed_payload,
                    "provider": provider.get("provider", "doubao"),
                    "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                    "used_remote": True,
                }
        except Exception:
            pass

        return {
            "storyboard": fallback_payload,
            "provider": provider.get("provider", "doubao"),
            "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
            "used_remote": False,
        }

    async def _complete_payload_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: dict[str, Any],
        provider_group: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        provider = self._resolve_provider_from_group(provider_group) if provider_group else self._resolve_provider()
        api_key = provider.get("api_key") or ""
        base_url = provider.get("base_url") or ""
        request_model = provider.get("request_model") or ""

        if not api_key or not base_url or not request_model:
            return {
                "payload": fallback_payload,
                "provider": provider.get("provider", "doubao"),
                "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                "used_remote": False,
            }

        payload = {
            "model": request_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        try:
            async with AsyncHttpClient(
                follow_redirects=True,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                request_timeout=60,
            ) as client:
                response = await client.fetch_post_json(
                    self._build_chat_completions_url(base_url),
                    json=payload,
                )
            content = self._extract_message_content(response)
            parsed_payload = self._extract_json_payload(content)
            if parsed_payload:
                return {
                    "payload": parsed_payload,
                    "provider": provider.get("provider", "doubao"),
                    "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
                    "used_remote": True,
                }
        except Exception:
            pass

        return {
            "payload": fallback_payload,
            "provider": provider.get("provider", "doubao"),
            "model": provider.get("display_model", DEFAULT_DOUBAO_MODEL_NAME),
            "used_remote": False,
        }

    def _resolve_provider(self) -> dict[str, str]:
        analysis_settings = SystemSettingsService().get_settings()["analysis"]
        providers = analysis_settings.get("providers", [])
        provider_map = {
            item.get("provider"): item
            for item in providers
            if isinstance(item, dict) and item.get("provider")
        }

        default_provider = provider_map.get(analysis_settings.get("default_provider", ""))
        if default_provider:
            return self._build_provider_payload(default_provider)

        for item in providers:
            if isinstance(item, dict) and item.get("api_key"):
                return self._build_provider_payload(item)

        return {
            "provider": "doubao",
            "api_key": os.getenv("DOUBAO_API_KEY", ""),
            "base_url": DEFAULT_DOUBAO_BASE_URL,
            "request_model": os.getenv("DOUBAO_ENDPOINT_ID", DEFAULT_DOUBAO_ENDPOINT_ID),
            "display_model": DEFAULT_DOUBAO_MODEL_NAME,
        }

    def _resolve_provider_from_group(self, group: dict[str, Any]) -> dict[str, str]:
        """Resolve provider from a specific settings group (e.g. motion_extraction)."""
        providers = group.get("providers", [])
        provider_map = {
            item.get("provider"): item
            for item in providers
            if isinstance(item, dict) and item.get("provider")
        }
        default_provider = provider_map.get(group.get("default_provider", ""))
        if default_provider and default_provider.get("api_key"):
            return self._build_provider_payload(default_provider)
        for item in providers:
            if isinstance(item, dict) and item.get("api_key"):
                return self._build_provider_payload(item)
        # Fallback to global analysis provider
        return self._resolve_provider()

    def _build_provider_payload(self, provider: dict[str, Any]) -> dict[str, str]:
        provider_key = str(provider.get("provider") or "analysis")
        if provider_key == "doubao":
            configured_model = (provider.get("default_model") or "").strip()
            return {
                "provider": "doubao",
                "api_key": provider.get("api_key") or os.getenv("DOUBAO_API_KEY", ""),
                "base_url": provider.get("base_url") or DEFAULT_DOUBAO_BASE_URL,
                "request_model": configured_model or os.getenv("DOUBAO_ENDPOINT_ID", DEFAULT_DOUBAO_ENDPOINT_ID),
                "display_model": configured_model or DEFAULT_DOUBAO_MODEL_NAME,
            }

        default_model = provider.get("default_model") or ""
        return {
            "provider": provider_key,
            "api_key": provider.get("api_key") or "",
            "base_url": provider.get("base_url") or "",
            "request_model": default_model,
            "display_model": default_model,
        }

    def _build_chat_completions_url(self, base_url: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            return "/chat/completions"

        if normalized.lower().endswith("/chat/completions"):
            return normalized

        return f"{normalized}/chat/completions"

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        fragments.append(text)
            return "\n".join(fragment for fragment in fragments if fragment).strip()

        return ""

    def _build_fallback_analysis(
        self,
        *,
        objective: str,
        source_name: str,
        source_analysis: dict[str, Any],
        timeline_segments: list[dict[str, Any]],
        script_overview: dict[str, Any],
        storyboard: dict[str, Any] | None,
    ) -> str:
        visual_summary = (
            (source_analysis.get("visual_features") or {}).get("summary")
            or "画面围绕主体和卖点进行快节奏切换。"
        )
        hook_segment = timeline_segments[0]["content"] if timeline_segments else "开场直接抛出核心卖点。"
        close_segment = timeline_segments[-1]["content"] if timeline_segments else "结尾用明确行动召唤推动转化。"
        storyboard_items = (storyboard or {}).get("items") or []
        storyboard_summary = (storyboard or {}).get("summary") or "分镜结果显示视频通过不同景别和动作切换维持节奏。"
        
        # Build Markdown Table for Storyboard
        storyboard_table = "| # | 时间 | 标题 | 镜头特征 | 画面描述 |\n|---|---|---|---|---|\n"
        if storyboard_items:
            for item in storyboard_items[:10]:
                idx = item.get("item_index", "?")
                start = item.get("start_ms", 0) / 1000.0
                end = item.get("end_ms", 0) / 1000.0
                title = item.get("title", "未命名")
                shot = f"{item.get('shot_type_code', 'medium')} / {item.get('camera_angle_code', 'eye_level')}"
                desc = item.get("visual_description", "无描述")
                storyboard_table += f"| {idx} | {start:.1f}s-{end:.1f}s | {title} | {shot} | {desc} |\n"
        else:
            storyboard_table = "当前未生成详细分镜条分。"

        return "\n".join(
            [
                "## 爆点总结",
                f"这条素材围绕“{objective or source_name}”建立短平快的带货节奏，通过视觉和文案的双重冲击实现高留存。",
                "",
                "## 开头钩子分析",
                f"**Hook 内容**：{hook_segment}",
                "前 3 秒快速切入核心利益点，利用强有力的视觉元素引导用户产生后续观看兴趣。",
                "",
                "## 画面与节奏分析",
                f"{visual_summary}\n\n**分镜概览**：{storyboard_summary}",
                "",
                "## 详细分镜拆解",
                storyboard_table,
                "",
                "## 脚本结构分析",
                f"**脚本全文**：\n{script_overview.get('full_text') or '未识别到完整脚本'}",
                "",
                "## 转化动作分析",
                f"**结尾 Call to Action**：{close_segment}",
                "通过明确的引导（如联系方式或型号展示）提示用户采取下一步行动。",
            ]
        )

    def _build_fallback_suggestions(
        self,
        *,
        objective: str,
        source_name: str,
    ) -> str:
        target = objective or source_name
        return "\n".join(
            [
                "1. 把前 3 秒的利益点再压缩，直接说清用户为什么要继续看，减少抽象铺垫。",
                f"2. 中段增加一处能证明“{target}”有效的特写或结果画面，提升信任感。",
                "3. 字幕改成更短的结果导向句式，让用户不静音也能快速抓住重点。",
                "4. 把结尾 CTA 从泛泛介绍改成具体动作，引导点击、咨询或下单。",
                "5. 在结构上增加一处前后对比或使用反馈，帮助转化逻辑闭环。",
            ]
        )

    def _build_fallback_storyboard(
        self,
        *,
        objective: str,
        source_name: str,
        shot_segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not shot_segments:
            return {
                "summary": f"围绕“{objective or source_name}”未检测到可用镜头段，已退回基础分镜结构。",
                "items": [],
            }

        items: list[dict[str, Any]] = []
        for index, segment in enumerate(shot_segments[:8], start=1):
            items.append(
                {
                    "item_index": index,
                    "title": segment.get("title")
                    or segment.get("action_hint")
                    or f"分镜 {index}",
                    "start_ms": int(segment.get("start_ms") or 0),
                    "end_ms": int(segment.get("end_ms") or 0),
                    "shot_type_code": segment.get("shot_type_code") or "medium",
                    "camera_angle_code": segment.get("camera_angle_code") or "eye_level",
                    "camera_motion_code": segment.get("camera_motion_code") or "static",
                    "visual_description": segment.get("visual_summary")
                    or segment.get("transcript_text")
                    or segment.get("ocr_text")
                    or "该镜头以主体展示为主，适合整理为结构化分镜。",
                    "source_segment_indexes": [int(segment.get("segment_index") or index)],
                    "confidence": float(segment.get("confidence") or 0.6),
                }
            )
        return {
            "summary": f"围绕“{objective or source_name}”共整理出 {len(items)} 条可展示分镜。",
            "items": items,
        }

    def _extract_json_payload(self, content: str) -> dict[str, Any] | None:
        normalized = (content or "").strip()
        if not normalized:
            return None

        candidates = [normalized]
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", normalized, flags=re.S | re.I)
        candidates.extend(block.strip() for block in fenced_blocks if block.strip())

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return payload

        start = normalized.find("{")
        end = normalized.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(normalized[start : end + 1])
            except json.JSONDecodeError:
                return None
            if isinstance(payload, dict):
                return payload
        return None
