import asyncio
import logging
import os
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_PROCESS_POOL: Executor | None = None


def _is_executor_shutdown(executor: Executor) -> bool:
    return bool(
        getattr(executor, "_shutdown_thread", False)
        or getattr(executor, "_shutdown", False)
    )


def get_process_pool() -> Executor:
    """Lazy initialize and return the global worker pool."""
    global _PROCESS_POOL
    if _PROCESS_POOL is not None and _is_executor_shutdown(_PROCESS_POOL):
        _PROCESS_POOL = None
    if _PROCESS_POOL is None:
        # We use a small number of workers because Whisper and SceneDetect are resource-heavy.
        # This prevents library conflicts (cv2/av) by keeping them in separate address spaces.
        max_workers = 2
        try:
            _PROCESS_POOL = ProcessPoolExecutor(max_workers=max_workers)
            logger.info("Initialized global ProcessPoolExecutor with %d workers", max_workers)
        except (NotImplementedError, OSError, PermissionError) as exc:
            logger.warning(
                "ProcessPoolExecutor unavailable, falling back to ThreadPoolExecutor: %s",
                exc,
            )
            _PROCESS_POOL = ThreadPoolExecutor(max_workers=max_workers)
            logger.info("Initialized fallback ThreadPoolExecutor with %d workers", max_workers)
    return _PROCESS_POOL


def shutdown_process_pool(*, wait: bool = True) -> None:
    global _PROCESS_POOL
    if _PROCESS_POOL is None:
        return

    executor = _PROCESS_POOL
    _PROCESS_POOL = None
    executor.shutdown(wait=wait)
    logger.info("Shut down global worker pool")


async def run_in_process(func: Callable[..., T], *args: Any) -> T:
    """Run a synchronous function in a separate child process using the global pool."""
    loop = asyncio.get_running_loop()
    pool = get_process_pool()
    return await loop.run_in_executor(pool, func, *args)


# --- Worker Functions (Must be top-level for pickling) ---

def run_shot_detection_worker(file_path: str, threshold: float, min_scene_len: int) -> list[dict[str, Any]]:
    """Isolated worker for PySceneDetect."""
    if not os.path.exists(file_path):
        return []

    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import ContentDetector

        video = open_video(file_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
        scene_manager.detect_scenes(video, show_progress=False)
        scene_list = scene_manager.get_scene_list()

        return [
            {
                "start_ms": int(start_time.get_seconds() * 1000),
                "end_ms": int(end_time.get_seconds() * 1000),
                "duration_ms": int((end_time.get_seconds() - start_time.get_seconds()) * 1000),
                "start_frame": int(start_time.get_frames()),
                "end_frame": int(end_time.get_frames()) - 1,
            }
            for start_time, end_time in scene_list
        ]
    except Exception as e:
        logger.error("Shot detection worker failed: %s", e)
        raise


def run_whisper_transcription_worker(
    file_path: str,
    model_source: str,
    device: str,
    compute_type: str,
    language: str | None = None,
    initial_prompt: str | None = None,
    beam_size: int = 5,
    vad_filter: bool = True,
) -> dict[str, Any]:
    """Isolated worker for faster-whisper."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_source, device=device, compute_type=compute_type)
        segments, info = model.transcribe(
            file_path,
            language=language,
            initial_prompt=initial_prompt,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )

        timeline_segments = []
        for index, segment in enumerate(segments, start=1):
            content = str(getattr(segment, "text", "") or "").strip()
            if not content:
                continue
            start_ms = int(float(getattr(segment, "start", 0.0) or 0.0) * 1000)
            end_ms = int(float(getattr(segment, "end", 0.0) or 0.0) * 1000)
            timeline_segments.append({
                "id": index,
                "segment_type": "speech",
                "speaker": "口播",
                "start_ms": max(0, start_ms),
                "end_ms": max(start_ms, end_ms),
                "content": content,
            })

        return {
            "timeline_segments": timeline_segments,
            "language": getattr(info, "language", None),
        }
    except Exception as e:
        logger.error("Whisper transcription worker failed: %s", e)
        raise
