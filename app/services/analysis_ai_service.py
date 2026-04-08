import os
from typing import Any

from app.http_client import AsyncHttpClient
from app.services.system_settings_service import SystemSettingsService


DEFAULT_DOUBAO_ENDPOINT_ID = "a604da88-88a8-4760-bd6a-015eff016604"
DEFAULT_DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_DOUBAO_MODEL_NAME = "doubao-seed-1-6-250615"


class AnalysisAIService:
    async def generate_analysis_reply(
        self,
        *,
        objective: str,
        source_name: str,
        source_analysis: dict[str, Any],
        timeline_segments: list[dict[str, Any]],
        script_overview: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = (
            "你是一名擅长 TikTok 电商短视频拆解的高级策略分析师。"
            "请输出清晰、专业、可执行的 Markdown 分析结果，聚焦钩子、节奏、镜头、脚本结构和转化逻辑。"
        )
        user_prompt = "\n".join(
            [
                f"分析目标：{objective or '请拆解视频脚本和转化结构'}",
                f"素材名称：{source_name}",
                f"画面特征：{source_analysis}",
                f"脚本片段：{timeline_segments}",
                f"脚本概览：{script_overview}",
                "请输出以下结构：爆点总结、开头钩子分析、画面与节奏分析、脚本结构分析、转化动作分析。",
            ]
        )
        fallback_content = self._build_fallback_analysis(
            objective=objective,
            source_name=source_name,
            source_analysis=source_analysis,
            timeline_segments=timeline_segments,
            script_overview=script_overview,
        )
        return await self._complete_markdown(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_content=fallback_content,
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
                    f"{base_url.rstrip('/')}/chat/completions",
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
            "content": "抱歉，回复生成失败。请检查网络或 AI 模型连接。",
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
                    f"{base_url.rstrip('/')}/chat/completions",
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

    def _resolve_provider(self) -> dict[str, str]:
        analysis_settings = SystemSettingsService().get_settings()["analysis"]
        providers = analysis_settings.get("providers", [])
        provider_map = {
            item.get("provider"): item
            for item in providers
            if isinstance(item, dict) and item.get("provider")
        }

        configured = provider_map.get("doubao")
        if configured and configured.get("enabled"):
            return {
                "provider": "doubao",
                "api_key": configured.get("api_key") or os.getenv("DOUBAO_API_KEY", ""),
                "base_url": configured.get("base_url") or DEFAULT_DOUBAO_BASE_URL,
                "request_model": os.getenv("DOUBAO_ENDPOINT_ID", DEFAULT_DOUBAO_ENDPOINT_ID),
                "display_model": configured.get("default_model") or DEFAULT_DOUBAO_MODEL_NAME,
            }

        default_provider = provider_map.get(analysis_settings.get("default_provider", ""))
        if default_provider and default_provider.get("enabled"):
            return {
                "provider": default_provider.get("provider", "analysis"),
                "api_key": default_provider.get("api_key") or "",
                "base_url": default_provider.get("base_url") or "",
                "request_model": default_provider.get("default_model") or "",
                "display_model": default_provider.get("default_model") or "",
            }

        return {
            "provider": "doubao",
            "api_key": os.getenv("DOUBAO_API_KEY", ""),
            "base_url": DEFAULT_DOUBAO_BASE_URL,
            "request_model": os.getenv("DOUBAO_ENDPOINT_ID", DEFAULT_DOUBAO_ENDPOINT_ID),
            "display_model": DEFAULT_DOUBAO_MODEL_NAME,
        }

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
    ) -> str:
        visual_summary = (
            (source_analysis.get("visual_features") or {}).get("summary")
            or "画面围绕主体和卖点进行快节奏切换。"
        )
        hook_segment = timeline_segments[0]["content"] if timeline_segments else "开场直接抛出核心卖点。"
        close_segment = timeline_segments[-1]["content"] if timeline_segments else "结尾用明确行动召唤推动转化。"
        return "\n".join(
            [
                "## 爆点总结",
                f"这条素材围绕“{objective or source_name}”建立短平快的带货节奏，适合做 TikTok 电商效果拆解。",
                "",
                "## 开头钩子分析",
                hook_segment,
                "",
                "## 画面与节奏分析",
                visual_summary,
                "",
                "## 脚本结构分析",
                script_overview.get("full_text") or "当前未识别到完整脚本，建议补充更清晰的视频音轨。",
                "",
                "## 转化动作分析",
                close_segment,
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
