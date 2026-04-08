import io
import wave

import pytest
from fastapi import UploadFile

from app.utils.file_utils import FileUtils


def _create_wav_file(file_path, duration_seconds: float = 1.0, frame_rate: int = 8000) -> None:
    total_frames = int(duration_seconds * frame_rate)
    with wave.open(str(file_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * total_frames)


@pytest.mark.asyncio
async def test_get_audio_duration_falls_back_to_wav(tmp_path) -> None:
    wav_path = tmp_path / "sample.wav"
    _create_wav_file(wav_path, duration_seconds=1.0)

    file_utils = FileUtils(temp_dir=str(tmp_path), ffprobe_binary="ffprobe")
    file_utils._get_duration_with_ffprobe = _raise_missing_ffprobe  # type: ignore[method-assign]

    duration = await file_utils.get_audio_duration(str(wav_path))

    assert duration == pytest.approx(1.0, rel=0.01)


@pytest.mark.asyncio
async def test_save_uploaded_file_enforces_max_size_during_stream(tmp_path) -> None:
    upload = UploadFile(
        file=io.BytesIO(b"a" * 12),
        filename="large.bin",
    )
    file_utils = FileUtils(temp_dir=str(tmp_path), max_file_size=10)

    with pytest.raises(ValueError, match="File size exceeds the limit"):
        await file_utils.save_uploaded_file(upload, "large.bin")

    assert list(tmp_path.iterdir()) == []
    await upload.close()


async def _raise_missing_ffprobe(_: str) -> float:
    raise FileNotFoundError
