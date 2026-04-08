import base64
import secrets
import time
import uuid
from dataclasses import dataclass
from threading import Lock


@dataclass
class CaptchaRecord:
    code: str
    expires_at: float


class CaptchaService:
    """
    简单的人机验证码服务。

    当前使用内存存储验证码，适合单实例服务；后续如果要多实例部署，
    可以把存储层替换成 Redis 之类的共享缓存。
    """

    CAPTCHA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

    def __init__(
        self,
        *,
        captcha_length: int = 5,
        ttl_seconds: int = 300,
        width: int = 160,
        height: int = 56,
    ) -> None:
        self.captcha_length = captcha_length
        self.ttl_seconds = ttl_seconds
        self.width = width
        self.height = height
        self._records: dict[str, CaptchaRecord] = {}
        self._lock = Lock()

    def create_captcha(self) -> dict[str, object]:
        """生成验证码并返回前端可直接使用的图片数据。"""
        captcha_id = uuid.uuid4().hex
        captcha_code = "".join(
            secrets.choice(self.CAPTCHA_ALPHABET)
            for _ in range(self.captcha_length)
        )
        expires_at = time.time() + self.ttl_seconds

        with self._lock:
            self._purge_expired_locked()
            self._records[captcha_id] = CaptchaRecord(
                code=captcha_code,
                expires_at=expires_at,
            )

        image_svg = self._build_svg(captcha_code)
        image_base64 = base64.b64encode(image_svg.encode("utf-8")).decode("ascii")

        return {
            "captcha_id": captcha_id,
            "captcha_type": "svg",
            "captcha_image": f"data:image/svg+xml;base64,{image_base64}",
            "expires_in_seconds": self.ttl_seconds,
        }

    def verify_captcha(self, captcha_id: str, captcha_code: str) -> bool:
        """校验验证码，校验成功后即失效。"""
        normalized_code = captcha_code.strip().upper()
        now = time.time()

        with self._lock:
            self._purge_expired_locked(now=now)
            record = self._records.get(captcha_id)
            if record is None:
                return False

            if record.expires_at <= now:
                self._records.pop(captcha_id, None)
                return False

            if not secrets.compare_digest(record.code, normalized_code):
                return False

            self._records.pop(captcha_id, None)
            return True

    def _purge_expired_locked(self, *, now: float | None = None) -> None:
        now = now or time.time()
        expired_ids = [
            captcha_id
            for captcha_id, record in self._records.items()
            if record.expires_at <= now
        ]
        for captcha_id in expired_ids:
            self._records.pop(captcha_id, None)

    def _build_svg(self, captcha_code: str) -> str:
        """生成简单的 SVG 验证码图片。"""
        background = '<rect width="100%" height="100%" rx="10" fill="#F7F4EA" />'

        line_nodes = []
        for _ in range(6):
            x1 = secrets.randbelow(self.width)
            y1 = secrets.randbelow(self.height)
            x2 = secrets.randbelow(self.width)
            y2 = secrets.randbelow(self.height)
            color = secrets.choice(["#C84C09", "#2A4E6C", "#557C55", "#7A3E65"])
            line_nodes.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="{color}" stroke-width="1.2" opacity="0.45" />'
            )

        dot_nodes = []
        for _ in range(18):
            cx = secrets.randbelow(self.width)
            cy = secrets.randbelow(self.height)
            radius = 1 + secrets.randbelow(2)
            dot_nodes.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#A67C52" opacity="0.35" />'
            )

        text_nodes = []
        start_x = 18
        step_x = 25
        for index, char in enumerate(captcha_code):
            x = start_x + index * step_x
            y = 36 + secrets.randbelow(8)
            rotation = secrets.choice([-18, -12, -6, 6, 12, 18])
            color = secrets.choice(["#7A1E00", "#0A4D68", "#3A5A40", "#5C2A9D"])
            font_size = 24 + secrets.randbelow(6)
            text_nodes.append(
                f'<text x="{x}" y="{y}" font-size="{font_size}" '
                f'font-family="Courier New, monospace" font-weight="700" '
                f'fill="{color}" transform="rotate({rotation} {x} {y})">{char}</text>'
            )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">'
            f"{background}"
            f"{''.join(line_nodes)}"
            f"{''.join(dot_nodes)}"
            f"{''.join(text_nodes)}"
            "</svg>"
        )


captcha_service = CaptchaService()
