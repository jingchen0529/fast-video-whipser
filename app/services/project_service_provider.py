"""Provider integrations for project workflows, including transcription, uploads, and video generation."""
from app.services.project_service_shared import *  # noqa: F401,F403


class ProjectProviderMixin:

    def _get_async_http_client_cls(self):
        from app.services import project_service as project_service_module
        return project_service_module.AsyncHttpClient

    async def _transcribe_source_media(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any],
    ) -> dict[str, Any]:
        settings_payload = SystemSettingsService().get_settings()
        transcription_group = settings_payload.get("transcription") or {}
        providers = transcription_group.get("providers") or []
        provider_map = {
            str(item.get("provider") or "").strip().lower(): item
            for item in providers
            if isinstance(item, dict) and str(item.get("provider") or "").strip()
        }
        provider_order = self._build_transcription_provider_order(
            default_provider=str(transcription_group.get("default_provider") or ""),
            provider_map=provider_map,
        )
        capabilities = SystemSettingsService().get_transcription_capabilities(
            payload=settings_payload,
        )
        provider_errors: list[str] = []

        for provider_key in provider_order:
            provider = provider_map.get(provider_key) or {}
            if not provider.get("enabled"):
                continue

            try:
                if provider_key == "faster_whisper":
                    capability = (
                        capabilities.get("providers", {})
                        .get("faster_whisper", {})
                    )
                    if not capability.get("available"):
                        issues = capability.get("issues") or ["当前环境不可用。"]
                        raise ValueError("；".join(str(item) for item in issues))

                    result = await self._transcribe_with_faster_whisper(
                        source_asset=source_asset,
                        provider=provider,
                    )
                    if result.get("timeline_segments"):
                        return {
                            **result,
                            "provider": provider_key,
                            "detail": f"已通过本地 faster-whisper 完成音频转写，共识别 {len(result['timeline_segments'])} 段内容。",
                        }

                if provider_key == "openai_whisper_api":
                    result = await self._transcribe_with_openai_api(
                        source_asset=source_asset,
                        provider=provider,
                    )
                    if result.get("timeline_segments"):
                        return {
                            **result,
                            "provider": provider_key,
                            "detail": f"已通过 OpenAI Whisper API 完成音频转写，共识别 {len(result['timeline_segments'])} 段内容。",
                        }
            except Exception as exc:
                label = provider.get("label") or provider_key
                provider_errors.append(f"{label}: {str(exc).strip() or '转写失败'}")

        raise ValueError(
            "音频转写失败。"
            + (" 已尝试以下引擎：" + " | ".join(provider_errors) if provider_errors else " 当前没有可用的转写引擎配置。")
        )

    def _build_transcription_provider_order(
        self,
        *,
        default_provider: str,
        provider_map: dict[str, dict[str, Any]],
    ) -> list[str]:
        normalized_default = (default_provider or "").strip().lower()
        order: list[str] = []
        if normalized_default:
            order.append(normalized_default)

        for provider_key, provider in provider_map.items():
            if provider_key in order or not provider.get("enabled"):
                continue
            order.append(provider_key)
        return order

    async def _transcribe_with_faster_whisper(
        self,
        *,
        source_asset: dict[str, Any],
        provider: dict[str, Any],
    ) -> dict[str, Any]:
        file_path = str(source_asset.get("file_path") or "").strip()
        if not file_path or not os.path.exists(file_path):
            raise ValueError("源视频文件不存在，无法执行本地转写。")

        model_source = self._resolve_faster_whisper_model_source(provider)
        language = (provider.get("language") or "").strip() or None
        initial_prompt = (provider.get("prompt") or "").strip() or None
        beam_size = int(provider.get("beam_size") or 5)
        vad_filter = bool(provider.get("vad_filter", True))
        resolved_device = self._resolve_faster_whisper_device(provider)
        resolved_compute_type = self._resolve_faster_whisper_compute_type(provider)

        from app.utils.process_pool import run_in_process, run_whisper_transcription_worker

        result = await run_in_process(
            run_whisper_transcription_worker,
            file_path,
            model_source,
            resolved_device,
            resolved_compute_type,
            language,
            initial_prompt,
            beam_size,
            vad_filter,
        )
        if result["timeline_segments"]:
            return result

        raise ValueError("faster-whisper 未识别到有效文本，请检查视频音轨或切换模型。")

    async def _transcribe_with_openai_api(
        self,
        *,
        source_asset: dict[str, Any],
        provider: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or "").strip()
        api_key = str(provider.get("api_key") or "").strip()
        model = str(provider.get("default_model") or "").strip() or "whisper-1"
        file_path = str(source_asset.get("file_path") or "").strip()

        if not base_url:
            raise ValueError("未配置 OpenAI Base URL。")
        if not api_key:
            raise ValueError("未配置 OpenAI API Key。")
        if not file_path or not os.path.exists(file_path):
            raise ValueError("源视频文件不存在，无法调用 OpenAI 转写接口。")

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 25:
            raise ValueError("OpenAI 音频转写接口当前仅支持 25MB 以内的单文件。")

        mime_type = (
            source_asset.get("mime_type")
            or mimetypes.guess_type(file_path)[0]
            or "application/octet-stream"
        )
        request_data: list[tuple[str, str]] = [("model", model)]
        language = str(provider.get("language") or "").strip()
        prompt = str(provider.get("prompt") or "").strip()
        response_format = "verbose_json" if model == "whisper-1" else "json"
        request_data.append(("response_format", response_format))
        if language:
            request_data.append(("language", language))
        if prompt:
            request_data.append(("prompt", prompt))
        if response_format == "verbose_json":
            request_data.append(("timestamp_granularities[]", "segment"))

        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            request_timeout=300,
        ) as client:
            with open(file_path, "rb") as file_obj:
                response = await client.fetch_data(
                    "POST",
                    f"{base_url.rstrip('/')}/audio/transcriptions",
                    data=request_data,
                    files={
                        "file": (
                            os.path.basename(file_path),
                            file_obj,
                            mime_type,
                        ),
                    },
                )

        payload = response.json()
        timeline_segments = self._extract_openai_transcription_segments(
            payload=payload,
            duration_ms=int(source_asset.get("duration_ms") or 0),
        )
        if timeline_segments:
            return {
                "timeline_segments": timeline_segments,
                "language": payload.get("language"),
            }

        raise ValueError("OpenAI 转写接口未返回有效文本，请检查模型或输入文件。")

    def _resolve_faster_whisper_model_source(self, provider: dict[str, Any]) -> str:
        default_model = str(provider.get("default_model") or "").strip() or "small"
        configured_model_path = Path(default_model)
        if configured_model_path.exists():
            return str(configured_model_path.resolve())

        model_dir_value = str(provider.get("model_dir") or "").strip()
        if not model_dir_value:
            return default_model

        model_dir = Path(model_dir_value)
        if not model_dir.is_absolute():
            model_dir = Path.cwd() / model_dir
        model_dir = model_dir.resolve()

        direct_candidate = model_dir / default_model
        if direct_candidate.exists():
            return str(direct_candidate)
        if model_dir.name == default_model and model_dir.exists():
            return str(model_dir)
        return default_model

    def _resolve_faster_whisper_device(self, provider: dict[str, Any]) -> str:
        requested = str(provider.get("device") or "auto").strip().lower()
        if requested not in {"", "auto"}:
            return requested

        capability = SystemSettingsService().get_transcription_capabilities()["providers"].get(
            "faster_whisper",
            {},
        )
        recommended_device = str(capability.get("recommended_device") or "").strip().lower()
        return recommended_device or "cpu"

    def _resolve_faster_whisper_compute_type(self, provider: dict[str, Any]) -> str:
        requested = str(provider.get("compute_type") or "auto").strip().lower()
        if requested not in {"", "auto", "default"}:
            return requested

        capability = SystemSettingsService().get_transcription_capabilities()["providers"].get(
            "faster_whisper",
            {},
        )
        recommended_compute_type = str(
            capability.get("recommended_compute_type") or ""
        ).strip().lower()
        return recommended_compute_type or "int8"

    def _extract_openai_transcription_segments(
        self,
        *,
        payload: dict[str, Any],
        duration_ms: int,
    ) -> list[dict[str, Any]]:
        raw_segments = payload.get("segments")
        if isinstance(raw_segments, list) and raw_segments:
            timeline_segments: list[dict[str, Any]] = []
            for index, segment in enumerate(raw_segments, start=1):
                if not isinstance(segment, dict):
                    continue
                content = str(segment.get("text") or "").strip()
                if not content:
                    continue
                start_ms = int(float(segment.get("start") or 0.0) * 1000)
                end_ms = int(float(segment.get("end") or 0.0) * 1000)
                timeline_segments.append(
                    {
                        "id": index,
                        "segment_type": "speech",
                        "speaker": "口播",
                        "start_ms": max(0, start_ms),
                        "end_ms": max(start_ms, end_ms),
                        "content": content,
                    }
                )
            if timeline_segments:
                return timeline_segments

        text = str(payload.get("text") or "").strip()
        if not text:
            return []

        return [
            {
                "id": 1,
                "segment_type": "speech",
                "speaker": "口播",
                "start_ms": 0,
                "end_ms": max(duration_ms, 1000),
                "content": text,
            }
        ]

    async def _ensure_source_asset(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        cached_asset = context.get("source_asset")
        if cached_asset:
            return cached_asset

        if project["source_asset_id"]:
            asset = AssetService().get_asset(asset_id=project["source_asset_id"])
            if asset is None:
                raise ValueError("已记录的源视频资产不存在，请重新上传素材。")
            asset["public_url"] = self._extract_asset_public_url(asset)
            context["source_asset"] = asset
            return asset

        validate_context = context.get("validate_video_link", {})
        remote_video_info = validate_context.get("remote_video_info") or {}
        download_url = validate_context.get("download_url") or project["source_url"]
        source_url = str(project.get("source_url") or "").strip()
        platform = self._detect_platform(source_url)
        if (
            not remote_video_info
            and source_url
            and platform == "tiktok"
            and not str(download_url or "").strip().lower().endswith(".mp4")
        ):
            crawler_result = await TikTokAPPCrawler().fetch_video_info(source_url)
            remote_video_info = crawler_result
            context.setdefault("validate_video_link", {})
            context["validate_video_link"]["remote_video_info"] = crawler_result
            context["validate_video_link"]["download_url"] = (
                crawler_result.get("download_url") or source_url
            )
            download_url = context["validate_video_link"]["download_url"]

            video_info = crawler_result.get("video_info") or {}
            source_name = (
                str(video_info.get("desc") or "").strip()
                or project.get("source_name")
                or source_url
            )
            self._update_project(
                project_id=project["id"],
                source_platform=platform,
                source_name=source_name,
                title=self._build_project_title(
                    source_name=source_name,
                    workflow_type=project["workflow_type"],
                ),
            )

        if not download_url:
            raise ValueError("缺少可下载的视频地址，无法继续执行视频分析。")

        async with FileUtils(
            temp_dir=str(self._project_upload_dir()),
            auto_delete=False,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            saved_path = await file_utils.download_file_from_url(download_url)

        size_bytes = os.path.getsize(saved_path)
        mime_type = mimetypes.guess_type(saved_path)[0] or "video/mp4"
        public_url = self._build_public_upload_url(saved_path)
        file_name = os.path.basename(saved_path)
        asset = AssetService().create_asset(
            owner_user_id=project["user_id"],
            asset_type="video",
            source_type="url",
            file_name=file_name,
            file_path=saved_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            metadata={
                "public_url": public_url,
                "source_url": project["source_url"],
                "download_url": download_url,
            },
        )
        asset["public_url"] = public_url
        self._update_project(
            project_id=project["id"],
            source_asset_id=asset["id"],
            media_url=public_url,
        )
        context["source_asset"] = asset
        return asset

    async def _persist_uploaded_asset(
        self,
        *,
        user_id: str,
        upload: UploadFile,
    ) -> dict[str, Any]:
        file_name = upload.filename or "upload.bin"
        content_type = upload.content_type or "application/octet-stream"
        async with FileUtils(
            temp_dir=str(self._project_upload_dir()),
            auto_delete=False,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            saved_path = await file_utils.save_uploaded_file(upload, file_name)

        size_bytes = os.path.getsize(saved_path)
        public_url = self._build_public_upload_url(saved_path)
        asset = AssetService().create_asset(
            owner_user_id=user_id,
            asset_type="video",
            source_type="upload",
            file_name=file_name,
            file_path=saved_path,
            mime_type=content_type,
            size_bytes=size_bytes,
            metadata={"public_url": public_url},
        )
        asset["public_url"] = public_url
        return asset

    def _project_upload_dir(self) -> Path:
        directory = Path("uploads") / "project-sources"
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()

    def _build_public_upload_url(self, file_path: str) -> str:
        uploads_root = Path("uploads").resolve()
        resolved_path = Path(file_path).resolve()
        relative_path = resolved_path.relative_to(uploads_root).as_posix()
        return f"/uploads/{relative_path}"

    def _extract_asset_public_url(self, asset: dict[str, Any]) -> str | None:
        metadata = asset.get("metadata_json") or {}
        public_url = metadata.get("public_url")
        if public_url:
            return str(public_url)

        file_path = asset.get("file_path")
        if not file_path:
            return None

        try:
            return self._build_public_upload_url(str(file_path))
        except ValueError:
            return None

    def _load_video_generation_state(self, *, project: dict[str, Any]) -> dict[str, Any]:
        raw_value = project.get("video_generation")
        if raw_value is None:
            raw_value = project.get("video_generation_json")
        return self._load_json_field(raw_value, DEFAULT_VIDEO_GENERATION)

    def _update_video_generation_state(
        self,
        *,
        project_id: int,
        project: dict[str, Any],
        **updates: Any,
    ) -> dict[str, Any]:
        state = self._load_video_generation_state(project=project)
        state.update(updates)
        state["updated_at"] = utcnow_ms()
        self._update_project(
            project_id=project_id,
            video_generation=state,
        )
        return state

    def _resolve_video_generation_provider(
        self,
        *,
        preferred_provider: str = "",
    ) -> dict[str, Any]:
        settings_payload = SystemSettingsService().get_settings()
        provider_group = settings_payload.get("remake") or {}
        raw_providers = provider_group.get("providers") or []
        providers = [
            item
            for item in raw_providers
            if isinstance(item, dict) and str(item.get("provider") or "").strip()
        ]
        if not providers:
            raise ValueError("系统未配置视频模型 provider，请先在设置页补齐 remake 配置。")

        provider_map = {
            str(item.get("provider") or "").strip().lower(): item
            for item in providers
        }
        preferred_key = str(preferred_provider or "").strip().lower()
        default_key = str(provider_group.get("default_provider") or "").strip().lower()

        candidate = None
        for key in (preferred_key, default_key):
            if not key:
                continue
            matched = provider_map.get(key)
            if matched and matched.get("enabled"):
                candidate = matched
                break
        if candidate is None:
            candidate = next((item for item in providers if item.get("enabled")), None)
        if candidate is None:
            candidate = providers[0]
        if not candidate.get("enabled"):
            raise ValueError("默认视频模型未启用，请先在系统设置中启用至少一个 remake provider。")
        return self._build_video_generation_provider_payload(candidate)

    def _build_video_generation_provider_payload(
        self,
        provider: dict[str, Any],
    ) -> dict[str, Any]:
        provider_key = str(provider.get("provider") or "").strip().lower()
        base_url = str(provider.get("base_url") or "").strip()
        if provider_key == "doubao" and not base_url:
            base_url = DEFAULT_DOUBAO_VIDEO_BASE_URL
        if provider_key == "kling" and not base_url:
            base_url = DEFAULT_KLING_VIDEO_BASE_URL
        if provider_key == "wanxiang" and not base_url:
            base_url = DEFAULT_WANXIANG_VIDEO_BASE_URL
        default_model = self._canonicalize_video_generation_model(
            provider_key=provider_key,
            model_name=str(provider.get("default_model") or "").strip(),
        )
        return {
            "provider": provider_key,
            "label": str(provider.get("label") or provider_key or "video"),
            "base_url": base_url,
            "api_key": str(provider.get("api_key") or "").strip(),
            "request_model": default_model,
            "display_model": default_model,
        }

    def _canonicalize_video_generation_model(
        self,
        *,
        provider_key: str,
        model_name: str,
    ) -> str:
        normalized = str(model_name or "").strip()
        if not normalized:
            return ""
        aliases = VIDEO_PROVIDER_MODEL_ALIASES.get(provider_key, {})
        return aliases.get(normalized.lower(), normalized)

    def _format_bearer_authorization(self, token: str) -> str:
        normalized = str(token or "").strip()
        if not normalized:
            raise ValueError("缺少 Bearer Token。")
        return normalized if normalized.lower().startswith("bearer ") else f"Bearer {normalized}"

    def _build_kling_authorization_value(self, api_key: str) -> str:
        normalized = str(api_key or "").strip()
        if not normalized:
            raise ValueError("未配置可灵 API Token。也可以填写 AccessKey:SecretKey。")
        if normalized.count(".") == 2 or normalized.lower().startswith("bearer "):
            return self._format_bearer_authorization(normalized)
        if ":" in normalized:
            access_key, secret_key = normalized.split(":", 1)
            if access_key.strip() and secret_key.strip():
                return self._format_bearer_authorization(
                    self._build_kling_jwt_token(
                        access_key=access_key.strip(),
                        secret_key=secret_key.strip(),
                    )
                )
        return self._format_bearer_authorization(normalized)

    def _build_kling_jwt_token(self, *, access_key: str, secret_key: str) -> str:
        issued_at = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "iss": access_key,
            "iat": issued_at,
            "nbf": max(0, issued_at - 5),
            "exp": issued_at + 30 * 60,
        }
        encoded_header = self._encode_jwt_segment(header)
        encoded_payload = self._encode_jwt_segment(payload)
        signing_input = f"{encoded_header}.{encoded_payload}"
        signature = hmac.new(
            secret_key.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        return f"{signing_input}.{encoded_signature}"

    def _encode_jwt_segment(self, value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).rstrip(b"=").decode("ascii")

    def _build_veo_submit_url(self, *, base_url: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized:
            raise ValueError(
                "Veo 需要配置完整的 Vertex AI publisher model endpoint，例如 "
                "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model_id}"
            )
        return normalized if normalized.endswith(":predictLongRunning") else f"{normalized}:predictLongRunning"

    def _build_veo_poll_url(self, *, base_url: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("Veo 需要配置完整的 Vertex AI publisher model endpoint。")
        if normalized.endswith(":fetchPredictOperation"):
            return normalized
        if normalized.endswith(":predictLongRunning"):
            return normalized[: -len(":predictLongRunning")] + ":fetchPredictOperation"
        return f"{normalized}:fetchPredictOperation"

    def _normalize_veo_resolution(self, resolution: str) -> str:
        normalized = str(resolution or "720P").strip().lower()
        if normalized in {"1080p", "720p"}:
            return normalized
        return "720p"

    def _normalize_veo_operation_status(
        self,
        *,
        payload: dict[str, Any],
        has_result: bool,
    ) -> str:
        if self._extract_nested_value(payload, "error", "response.error"):
            return "failed"
        done = self._extract_nested_value(payload, "done", "response.done")
        if done is True:
            return "succeeded" if has_result else "failed"
        return "running"

    def _filter_remote_media_urls(self, values: list[str]) -> list[str]:
        return [
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip().startswith(("http://", "https://"))
        ]

    def _extract_generation_source_url(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any] | None,
    ) -> str:
        candidates: list[str] = []
        if source_asset:
            metadata = source_asset.get("metadata_json") or {}
            if isinstance(metadata, dict):
                candidates.extend(
                    [
                        str(metadata.get("download_url") or "").strip(),
                        str(metadata.get("source_url") or "").strip(),
                    ]
                )
        candidates.append(str(project.get("source_url") or "").strip())
        for candidate in candidates:
            if candidate.startswith(("http://", "https://")):
                return candidate
        return ""

    async def _submit_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        provider_key = provider.get("provider")
        if provider_key == "doubao":
            return await self._submit_doubao_video_generation_task(
                provider=provider,
                request_payload=request_payload,
            )
        if provider_key == "kling":
            return await self._submit_kling_video_generation_task(
                provider=provider,
                request_payload=request_payload,
            )
        if provider_key == "veo":
            return await self._submit_veo_video_generation_task(
                provider=provider,
                request_payload=request_payload,
            )
        if provider_key == "wanxiang":
            return await self._submit_wanxiang_video_generation_task(
                provider=provider,
                request_payload=request_payload,
            )
        return await self._submit_generic_video_generation_task(
            provider=provider,
            request_payload=request_payload,
        )

    async def _submit_doubao_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        submit_url = self._build_doubao_video_task_url(
            base_url=str(provider.get("base_url") or DEFAULT_DOUBAO_VIDEO_BASE_URL),
        )
        api_key = str(provider.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("未配置豆包视频模型 API Key。")
        payload = {
            "model": provider.get("request_model"),
            "content": [
                {
                    "type": "text",
                    "text": request_payload.get("prompt"),
                }
            ],
            "duration": int(request_payload.get("duration_seconds") or 5),
            "ratio": request_payload.get("aspect_ratio") or "9:16",
        }
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_post_json(
                submit_url,
                json=payload,
            )
        task_id = self._extract_nested_value(
            response,
            "id",
            "task_id",
            "data.id",
            "data.task_id",
        )
        result_video_url = self._extract_result_video_url(response)
        status = self._normalize_video_task_status(
            self._extract_task_status(response),
            has_result=bool(result_video_url),
        )
        return {
            "provider_task_id": str(task_id or ""),
            "status": status,
            "result_video_url": result_video_url,
            "raw_response": response,
        }

    async def _submit_kling_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or DEFAULT_KLING_VIDEO_BASE_URL).rstrip("/")
        submit_url = (
            base_url
            if base_url.endswith("/v1/videos/text2video")
            else f"{base_url}/v1/videos/text2video"
        )
        payload = {
            "model_name": provider.get("request_model") or "kling-v3",
            "prompt": request_payload.get("prompt"),
            "negative_prompt": request_payload.get("negative_prompt"),
            "mode": "pro",
            "aspect_ratio": request_payload.get("aspect_ratio") or "9:16",
            "duration": str(max(3, min(15, int(request_payload.get("duration_seconds") or 5)))),
        }
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._build_kling_authorization_value(
                    str(provider.get("api_key") or "")
                ),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_post_json(
                submit_url,
                json=payload,
            )
        task_id = self._extract_nested_value(
            response,
            "task_id",
            "data.task_id",
            "id",
            "data.id",
        )
        result_video_url = self._extract_result_video_url(response)
        status = self._normalize_video_task_status(
            self._extract_task_status(response),
            has_result=bool(result_video_url),
        )
        return {
            "provider_task_id": str(task_id or ""),
            "status": status,
            "result_video_url": result_video_url,
            "raw_response": response,
        }

    async def _submit_veo_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        submit_url = self._build_veo_submit_url(
            base_url=str(provider.get("base_url") or "").strip(),
        )
        api_key = str(provider.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("未配置 Veo Bearer Token。")
        duration_seconds = int(request_payload.get("duration_seconds") or 5)
        payload = {
            "instances": [
                {
                    "prompt": request_payload.get("prompt"),
                }
            ],
            "parameters": {
                "sampleCount": 1,
                "durationSeconds": duration_seconds,
                "aspectRatio": request_payload.get("aspect_ratio") or "9:16",
                "negativePrompt": request_payload.get("negative_prompt") or "",
                "resolution": self._normalize_veo_resolution(
                    str(request_payload.get("resolution") or "720P")
                ),
            },
        }
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_post_json(
                submit_url,
                json=payload,
            )
        task_id = self._extract_nested_value(
            response,
            "name",
            "operation.name",
        )
        result_video_url = self._extract_result_video_url(response)
        inline_video_bytes = self._extract_inline_video_bytes(response)
        status = self._normalize_veo_operation_status(
            payload=response,
            has_result=bool(result_video_url or inline_video_bytes),
        )
        return {
            "provider_task_id": str(task_id or ""),
            "status": status,
            "result_video_url": result_video_url,
            "inline_video_bytes": inline_video_bytes,
            "raw_response": response,
        }

    async def _submit_wanxiang_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or DEFAULT_WANXIANG_VIDEO_BASE_URL).rstrip("/")
        submit_url = (
            base_url
            if "/video-synthesis" in base_url
            else f"{base_url}/api/v1/services/aigc/video-generation/video-synthesis"
        )
        api_key = str(provider.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("未配置万相视频模型 API Key。")
        payload = {
            "model": provider.get("request_model"),
            "input": {
                "prompt": request_payload.get("prompt"),
            },
            "parameters": {
                "duration": int(request_payload.get("duration_seconds") or 5),
                "resolution": request_payload.get("resolution") or "720P",
                "watermark": False,
            },
        }
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_post_json(
                submit_url,
                json=payload,
            )
        task_id = self._extract_nested_value(
            response,
            "output.task_id",
            "task_id",
            "data.task_id",
            "id",
        )
        result_video_url = self._extract_result_video_url(response)
        status = self._normalize_video_task_status(
            self._extract_task_status(response),
            has_result=bool(result_video_url),
        )
        return {
            "provider_task_id": str(task_id or ""),
            "status": status,
            "result_video_url": result_video_url,
            "raw_response": response,
        }

    async def _submit_generic_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or "").rstrip("/")
        api_key = str(provider.get("api_key") or "").strip()
        if not base_url:
            raise ValueError("当前视频模型未配置 Base URL。")
        submit_url = base_url if any(
            token in base_url for token in ("/tasks", "/generations", "/video-synthesis")
        ) else f"{base_url}/tasks"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = self._format_bearer_authorization(api_key)
        payload = {
            "model": provider.get("request_model"),
            "prompt": request_payload.get("prompt"),
            "negative_prompt": request_payload.get("negative_prompt"),
            "task_type": "video_generation",
            "input": {
                "prompt": request_payload.get("prompt"),
                "negative_prompt": request_payload.get("negative_prompt"),
                "source_url": request_payload.get("source_url") or "",
                "reference_frames": request_payload.get("reference_frames") or [],
                "storyboard": request_payload.get("storyboard") or {},
                "script": request_payload.get("script") or {},
            },
            "parameters": {
                "duration": int(request_payload.get("duration_seconds") or 5),
                "aspect_ratio": request_payload.get("aspect_ratio") or "9:16",
                "resolution": request_payload.get("resolution") or "720P",
                "mode": request_payload.get("mode") or "create",
            },
        }
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers=headers,
            request_timeout=120,
        ) as client:
            response = await client.fetch_post_json(
                submit_url,
                json=payload,
            )
        task_id = self._extract_nested_value(
            response,
            "task_id",
            "id",
            "data.task_id",
            "data.id",
            "output.task_id",
        )
        result_video_url = self._extract_result_video_url(response)
        status = self._normalize_video_task_status(
            self._extract_task_status(response),
            has_result=bool(result_video_url),
        )
        return {
            "provider_task_id": str(task_id or ""),
            "status": status,
            "result_video_url": result_video_url,
            "raw_response": response,
        }

    async def _wait_for_video_generation_result(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
        existing_result_url: str = "",
        max_attempts: int = 45,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        if existing_result_url:
            return {
                "status": "succeeded",
                "provider_task_id": provider_task_id,
                "result_video_url": existing_result_url,
                "error_detail": None,
                "raw_response": {},
            }
        if not provider_task_id:
            raise ValueError("视频模型未返回 provider_task_id，无法继续轮询。")

        last_result: dict[str, Any] = {}
        for _ in range(max_attempts):
            poll_result = await self._poll_video_generation_task(
                provider=provider,
                provider_task_id=provider_task_id,
            )
            last_result = poll_result
            if poll_result["status"] == "succeeded":
                return poll_result
            if poll_result["status"] == "failed":
                raise ValueError(poll_result.get("error_detail") or "第三方视频生成失败。")
            await asyncio.sleep(poll_interval_seconds)
        raise ValueError(
            last_result.get("error_detail")
            or "视频生成超时，请稍后重试或检查第三方任务状态。"
        )

    async def _poll_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
    ) -> dict[str, Any]:
        provider_key = provider.get("provider")
        if provider_key == "doubao":
            return await self._poll_doubao_video_generation_task(
                provider=provider,
                provider_task_id=provider_task_id,
            )
        if provider_key == "kling":
            return await self._poll_kling_video_generation_task(
                provider=provider,
                provider_task_id=provider_task_id,
            )
        if provider_key == "veo":
            return await self._poll_veo_video_generation_task(
                provider=provider,
                provider_task_id=provider_task_id,
            )
        if provider_key == "wanxiang":
            return await self._poll_wanxiang_video_generation_task(
                provider=provider,
                provider_task_id=provider_task_id,
            )
        return await self._poll_generic_video_generation_task(
            provider=provider,
            provider_task_id=provider_task_id,
        )

    async def _poll_doubao_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
    ) -> dict[str, Any]:
        poll_url = self._build_doubao_video_task_url(
            base_url=str(provider.get("base_url") or DEFAULT_DOUBAO_VIDEO_BASE_URL),
            provider_task_id=provider_task_id,
        )
        api_key = str(provider.get("api_key") or "").strip()
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_get_json(poll_url)
        result_video_url = self._extract_result_video_url(response)
        return {
            "status": self._normalize_video_task_status(
                self._extract_task_status(response),
                has_result=bool(result_video_url),
            ),
            "provider_task_id": provider_task_id,
            "result_video_url": result_video_url,
            "cover_url": self._extract_cover_url(response),
            "error_detail": self._extract_error_detail(response),
            "raw_response": response,
        }

    def _build_doubao_video_task_url(
        self,
        *,
        base_url: str,
        provider_task_id: str | None = None,
    ) -> str:
        normalized_base, task_path = self._resolve_doubao_video_task_endpoint(
            base_url=base_url,
        )
        task_url = f"{normalized_base}{task_path}"
        if provider_task_id:
            return f"{task_url.rstrip('/')}/{provider_task_id}"
        return task_url

    def _resolve_doubao_video_task_endpoint(
        self,
        *,
        base_url: str,
    ) -> tuple[str, str]:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized:
            normalized = DEFAULT_DOUBAO_VIDEO_BASE_URL

        lowered = normalized.lower()
        for task_path in DOUBAO_VIDEO_TASK_PATHS:
            if lowered.endswith(task_path):
                return normalized[: -len(task_path)], task_path

        if "ark.cn-beijing.volces.com" in lowered or lowered.endswith("/api/v3"):
            return normalized, "/contents/generations/tasks"

        return normalized, "/api/v1/contents/generations/tasks"

    async def _poll_kling_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or DEFAULT_KLING_VIDEO_BASE_URL).rstrip("/")
        poll_url = (
            f"{base_url}/{provider_task_id}"
            if base_url.endswith("/v1/videos/text2video")
            else f"{base_url}/v1/videos/text2video/{provider_task_id}"
        )
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._build_kling_authorization_value(
                    str(provider.get("api_key") or "")
                ),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_get_json(poll_url)
        result_video_url = self._extract_result_video_url(response)
        return {
            "status": self._normalize_video_task_status(
                self._extract_task_status(response),
                has_result=bool(result_video_url),
            ),
            "provider_task_id": provider_task_id,
            "result_video_url": result_video_url,
            "cover_url": self._extract_cover_url(response),
            "error_detail": self._extract_error_detail(response),
            "raw_response": response,
        }

    async def _poll_veo_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
    ) -> dict[str, Any]:
        poll_url = self._build_veo_poll_url(
            base_url=str(provider.get("base_url") or "").strip(),
        )
        api_key = str(provider.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("未配置 Veo Bearer Token。")
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_post_json(
                poll_url,
                json={"operationName": provider_task_id},
            )
        result_video_url = self._extract_result_video_url(response)
        inline_video_bytes = self._extract_inline_video_bytes(response)
        return {
            "status": self._normalize_veo_operation_status(
                payload=response,
                has_result=bool(result_video_url or inline_video_bytes),
            ),
            "provider_task_id": provider_task_id,
            "result_video_url": result_video_url,
            "inline_video_bytes": inline_video_bytes,
            "cover_url": self._extract_cover_url(response),
            "error_detail": self._extract_error_detail(response),
            "raw_response": response,
        }

    async def _poll_wanxiang_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or DEFAULT_WANXIANG_VIDEO_BASE_URL).rstrip("/")
        parsed = urlparse(base_url)
        root_url = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else base_url
        ).rstrip("/")
        poll_url = f"{root_url}/api/v1/tasks/{provider_task_id}"
        api_key = str(provider.get("api_key") or "").strip()
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Content-Type": "application/json",
            },
            request_timeout=120,
        ) as client:
            response = await client.fetch_get_json(poll_url)
        result_video_url = self._extract_result_video_url(response)
        return {
            "status": self._normalize_video_task_status(
                self._extract_task_status(response),
                has_result=bool(result_video_url),
            ),
            "provider_task_id": provider_task_id,
            "result_video_url": result_video_url,
            "cover_url": self._extract_cover_url(response),
            "error_detail": self._extract_error_detail(response),
            "raw_response": response,
        }

    async def _poll_generic_video_generation_task(
        self,
        *,
        provider: dict[str, Any],
        provider_task_id: str,
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or "").rstrip("/")
        api_key = str(provider.get("api_key") or "").strip()
        if not base_url:
            raise ValueError("当前视频模型未配置 Base URL。")
        if any(token in base_url for token in ("/tasks", "/generations", "/video-synthesis")):
            poll_url = f"{base_url.rstrip('/')}/{provider_task_id}"
        else:
            poll_url = f"{base_url}/tasks/{provider_task_id}"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = self._format_bearer_authorization(api_key)
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers=headers,
            request_timeout=120,
        ) as client:
            response = await client.fetch_get_json(poll_url)
        result_video_url = self._extract_result_video_url(response)
        return {
            "status": self._normalize_video_task_status(
                self._extract_task_status(response),
                has_result=bool(result_video_url),
            ),
            "provider_task_id": provider_task_id,
            "result_video_url": result_video_url,
            "cover_url": self._extract_cover_url(response),
            "error_detail": self._extract_error_detail(response),
            "raw_response": response,
        }

    def _extract_nested_value(
        self,
        payload: dict[str, Any],
        *paths: str,
    ) -> Any:
        for path in paths:
            current: Any = payload
            for part in path.split("."):
                if isinstance(current, dict):
                    current = current.get(part)
                    continue
                if isinstance(current, list) and part.isdigit():
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                        continue
                current = None
                break
            if current not in (None, "", []):
                return current
        return None

    def _extract_task_status(self, payload: dict[str, Any]) -> str:
        value = self._extract_nested_value(
            payload,
            "status",
            "state",
            "task_status",
            "output.task_status",
            "output.status",
            "data.status",
            "data.state",
            "data.task_status",
            "result.status",
        )
        return str(value or "").strip()

    def _extract_result_video_url(self, payload: dict[str, Any]) -> str:
        value = self._extract_nested_value(
            payload,
            "result_video_url",
            "video_url",
            "output.video_url",
            "content.video_url",
            "data.video_url",
            "data.result_video_url",
            "data.content.video_url",
            "output.results.0.video_url",
            "output.results.0.url",
            "task_result.videos.0.url",
            "task_result.videos.0.video_url",
            "data.task_result.videos.0.url",
            "data.task_result.videos.0.video_url",
            "response.videos.0.gcsUri",
            "response.videos.0.uri",
            "response.generatedVideos.0.video.uri",
            "result.video_url",
            "result.url",
        )
        return str(value or "").strip()

    def _extract_inline_video_bytes(self, payload: dict[str, Any]) -> str:
        value = self._extract_nested_value(
            payload,
            "inline_video_bytes",
            "video_bytes_base64",
            "response.videos.0.bytesBase64Encoded",
            "response.generatedVideos.0.video.bytesBase64Encoded",
            "videos.0.bytesBase64Encoded",
            "generatedVideos.0.video.bytesBase64Encoded",
        )
        return str(value or "").strip()

    def _extract_cover_url(self, payload: dict[str, Any]) -> str:
        value = self._extract_nested_value(
            payload,
            "cover_url",
            "output.cover_url",
            "content.poster_url",
            "content.last_frame_url",
            "output.results.0.cover_url",
            "task_result.videos.0.cover_url",
            "data.task_result.videos.0.cover_url",
            "result.cover_url",
        )
        return str(value or "").strip()

    def _extract_error_detail(self, payload: dict[str, Any]) -> str:
        value = self._extract_nested_value(
            payload,
            "error_detail",
            "error_message",
            "message",
            "msg",
            "output.message",
            "output.error_message",
            "data.error_message",
            "error.message",
            "response.error.message",
            "result.error_message",
        )
        return str(value or "").strip()

    def _normalize_video_task_status(
        self,
        raw_status: str,
        *,
        has_result: bool,
    ) -> str:
        normalized = str(raw_status or "").strip().lower()
        if has_result and not normalized:
            return "succeeded"
        if normalized in {"succeeded", "success", "successful", "succeed", "done", "completed", "finished"}:
            return "succeeded"
        if normalized in {"failed", "error", "cancelled", "canceled"}:
            return "failed"
        if normalized in {"", "queued", "pending", "submitted", "running", "processing", "in_progress"}:
            return "running"
        return "running"

    async def _persist_generated_video_asset(
        self,
        *,
        project: dict[str, Any],
        request_payload: dict[str, Any],
        provider: dict[str, Any],
        generation_result: dict[str, Any],
    ) -> dict[str, Any]:
        result_video_url = str(generation_result.get("result_video_url") or "").strip()
        inline_video_bytes = str(generation_result.get("inline_video_bytes") or "").strip()
        if not result_video_url and not inline_video_bytes:
            raise ValueError("第三方已完成任务，但未返回可下载的视频地址或内联视频内容。")

        downloaded_path = await self._materialize_generated_video_file(
            provider=provider,
            generation_result=generation_result,
        )

        target_dir = self._generated_upload_dir()
        target_name = self._build_generated_asset_name(
            workflow_type=project.get("workflow_type") or "create",
            download_url=result_video_url,
        )
        target_path = target_dir / target_name
        if target_path.exists():
            target_path = target_dir / f"{target_path.stem}-{uuid.uuid4().hex[:6]}{target_path.suffix}"
        if Path(downloaded_path).resolve() != target_path.resolve():
            shutil.move(downloaded_path, target_path)

        source_asset = None
        if project.get("source_asset_id"):
            source_asset = AssetService().get_asset(asset_id=project["source_asset_id"])
        duration_ms, width, height = self._resolve_generated_video_dimensions(
            request_payload=request_payload,
            generation_result=generation_result,
            source_asset=source_asset,
        )
        file_name = target_path.name
        mime_type = mimetypes.guess_type(str(target_path))[0] or "video/mp4"
        size_bytes = os.path.getsize(target_path)
        public_url = self._build_public_upload_url(str(target_path))
        asset = AssetService().create_asset(
            owner_user_id=project["user_id"],
            asset_type="video",
            source_type="generated",
            file_name=file_name,
            file_path=str(target_path),
            mime_type=mime_type,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            width=width,
            height=height,
            metadata={
                "public_url": public_url,
                "provider": provider.get("provider"),
                "model": provider.get("display_model"),
                "provider_task_id": generation_result.get("provider_task_id"),
                "result_video_url": result_video_url,
                "inline_video_bytes": bool(inline_video_bytes),
                "cover_url": generation_result.get("cover_url"),
                "project_id": project["id"],
                "source_asset_id": project.get("source_asset_id"),
            },
        )
        asset["public_url"] = public_url
        return asset

    async def _materialize_generated_video_file(
        self,
        *,
        provider: dict[str, Any],
        generation_result: dict[str, Any],
    ) -> str:
        inline_video_bytes = str(generation_result.get("inline_video_bytes") or "").strip()
        if inline_video_bytes:
            target_path = self._generated_upload_dir() / f"inline-{uuid.uuid4().hex[:8]}.mp4"
            try:
                target_path.write_bytes(base64.b64decode(inline_video_bytes))
            except (ValueError, TypeError) as exc:
                raise ValueError("Veo 返回的内联视频内容无法解码。") from exc
            return str(target_path)

        result_video_url = str(generation_result.get("result_video_url") or "").strip()
        if result_video_url.startswith("gs://"):
            return await self._download_gcs_generated_video(
                provider=provider,
                gcs_uri=result_video_url,
            )

        async with FileUtils(
            temp_dir=str(self._generated_upload_dir()),
            auto_delete=False,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            return await file_utils.download_file_from_url(result_video_url)

    async def _download_gcs_generated_video(
        self,
        *,
        provider: dict[str, Any],
        gcs_uri: str,
    ) -> str:
        bucket, object_name = self._parse_gcs_uri(gcs_uri)
        api_key = str(provider.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("下载 Veo GCS 结果前需要配置 Bearer Token。")
        download_url = (
            f"https://storage.googleapis.com/download/storage/v1/b/{quote(bucket, safe='')}"
            f"/o/{quote(object_name, safe='')}?alt=media"
        )
        target_path = self._generated_upload_dir() / f"gcs-{uuid.uuid4().hex[:8]}.mp4"
        async with self._get_async_http_client_cls()(
            follow_redirects=True,
            headers={
                "Authorization": self._format_bearer_authorization(api_key),
                "Accept": "*/*",
            },
            request_timeout=300,
        ) as client:
            await client.download_file(download_url, str(target_path))
        return str(target_path)

    def _parse_gcs_uri(self, gcs_uri: str) -> tuple[str, str]:
        normalized = str(gcs_uri or "").strip()
        if not normalized.startswith("gs://"):
            raise ValueError("无效的 GCS URI。")
        bucket_and_object = normalized[5:]
        if "/" not in bucket_and_object:
            raise ValueError("GCS URI 缺少对象路径。")
        bucket, object_name = bucket_and_object.split("/", 1)
        if not bucket or not object_name:
            raise ValueError("GCS URI 缺少 bucket 或对象路径。")
        return bucket, object_name

    def _resolve_generated_video_dimensions(
        self,
        *,
        request_payload: dict[str, Any],
        generation_result: dict[str, Any],
        source_asset: dict[str, Any] | None,
    ) -> tuple[int | None, int | None, int | None]:
        duration_ms = self._safe_int(
            self._extract_nested_value(
                generation_result.get("raw_response") or {},
                "usage.video_duration",
                "usage.duration_ms",
                "output.duration_ms",
                "result.duration_ms",
            )
        )
        if duration_ms <= 0:
            duration_ms = int(request_payload.get("duration_seconds") or 5) * 1000

        if source_asset and source_asset.get("width") and source_asset.get("height"):
            return duration_ms, int(source_asset["width"]), int(source_asset["height"])

        aspect_ratio = str(request_payload.get("aspect_ratio") or "9:16")
        if aspect_ratio == "16:9":
            return duration_ms, 1280, 720
        if aspect_ratio == "1:1":
            return duration_ms, 720, 720
        return duration_ms, 720, 1280

    def _generated_upload_dir(self) -> Path:
        directory = Path("uploads") / "generated"
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()

    def _build_generated_asset_name(
        self,
        *,
        workflow_type: str,
        download_url: str,
    ) -> str:
        date_part = utcnow().strftime("%Y%m%d")
        extension = Path(urlparse(download_url).path).suffix or ".mp4"
        prefix = "viral-remake" if workflow_type == "remake" else "viral-create"
        return f"{prefix}-{date_part}-{uuid.uuid4().hex[:6]}{extension}"
