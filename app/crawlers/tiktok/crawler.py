import re
import time
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlencode

from app.http_client import AsyncHttpClient


class TikTokAPPCrawler:
    """
    TikTok 爬虫，负责解析作品 ID、获取视频信息以及提取下载链接。
    """

    VIDEO_ID_PATTERN = re.compile(r"(?:video|photo)/(\d+)")
    NUMERIC_ID_PATTERN = re.compile(r"^\d{8,}$")
    # 直接内联 TikTok feed 接口地址，避免再维护单独的 endpoints.py。
    TIKTOK_API_BASE_URL = "https://api22-normal-c-alisg.tiktokv.com"
    HOME_FEED_URL = f"{TIKTOK_API_BASE_URL}/aweme/v1/feed/"
    # 这里只保留当前单视频查询实际使用的请求参数，替代原来的 models.py。
    FEED_QUERY_DEFAULTS = {
        "iid": 7318518857994389254,
        "device_id": 7318517321748022790,
        "channel": "googleplay",
        "app_name": "musical_ly",
        "version_code": "300904",
        "device_platform": "android",
        "device_type": "SM-ASUS_Z01QD",
        "os_version": "9",
    }

    def __init__(
        self,
        *,
        http_client_factory: Optional[Callable[..., AsyncHttpClient]] = None,
    ) -> None:
        self.http_client_factory = http_client_factory or AsyncHttpClient

    @staticmethod
    def get_tiktok_headers() -> dict[str, str]:
        """构造访问 TikTok 时使用的基础请求头。"""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
            "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
        }

    @staticmethod
    def params_to_query_string(params: Mapping[str, Any]) -> str:
        """将参数字典转换为 URL 查询字符串。"""
        return urlencode(
            {
                key: value
                for key, value in params.items()
                if value is not None
            }
        )

    @classmethod
    def build_feed_query_params(cls, aweme_id: str) -> dict[str, Any]:
        """构造单个作品详情查询所需的 feed 参数。"""
        # 将 feed 请求参数集中在这里，后续要裁剪字段时只需要改这一处。
        return {
            **cls.FEED_QUERY_DEFAULTS,
            "aweme_id": aweme_id,
        }

    @classmethod
    def extract_aweme_id_from_text(cls, value: str) -> Optional[str]:
        """从作品 ID、视频链接或分享链接中提取 aweme_id。"""
        value = value.strip()
        if cls.NUMERIC_ID_PATTERN.fullmatch(value):
            return value

        match = cls.VIDEO_ID_PATTERN.search(value)
        if match:
            return match.group(1)

        return None

    def _create_client(self, **kwargs: Any) -> AsyncHttpClient:
        return self.http_client_factory(**kwargs)

    async def resolve_aweme_id(self, value: str) -> str:
        """优先直接提取作品 ID，提取不到时再跟随跳转解析真实链接。"""
        aweme_id = self.extract_aweme_id_from_text(value)
        if aweme_id:
            return aweme_id

        headers = self.get_tiktok_headers()
        async with self._create_client(headers=headers, follow_redirects=True) as client:
            response = await client.fetch_response(value)
            resolved_url = str(response.url)

        aweme_id = self.extract_aweme_id_from_text(resolved_url)
        if aweme_id:
            return aweme_id

        raise ValueError("Invalid TikTok video URL or aweme_id.")

    async def resolve_video_data(self, value: str) -> dict[str, Any]:
        """统一根据作品 ID 或链接拉取单条视频原始数据。"""
        aweme_id = self.extract_aweme_id_from_text(value)
        if aweme_id:
            return await self.fetch_one_video(aweme_id)

        return await self.fetch_one_video_by_url(value)

    async def fetch_one_video(self, aweme_id: str) -> dict[str, Any]:
        """按作品 ID 请求 TikTok feed 接口并返回目标视频数据。"""
        headers = self.get_tiktok_headers()
        params = self.build_feed_query_params(aweme_id)
        param_str = self.params_to_query_string(params)
        url = f"{self.HOME_FEED_URL}?{param_str}"

        async with self._create_client(headers=headers, follow_redirects=True) as client:
            response = await client.fetch_get_json(url)

        aweme_list = response.get("aweme_list") or []
        if not aweme_list:
            raise ValueError("No TikTok video data found for the requested aweme_id.")

        for item in aweme_list:
            if item.get("aweme_id") == aweme_id:
                return item

        raise ValueError("Requested aweme_id was not found in the TikTok API response.")

    async def fetch_one_video_by_url(self, url: str) -> dict[str, Any]:
        """先解析链接中的作品 ID，再拉取视频数据。"""
        aweme_id = await self.resolve_aweme_id(url)
        return await self.fetch_one_video(aweme_id)

    @staticmethod
    def extract_download_url(video_data: dict[str, Any]) -> str:
        """优先选择播放地址，尽量规避可能带水印的下载地址。"""
        video = video_data.get("video") or {}

        candidates = [
            video.get("play_addr", {}).get("url_list", []),
            video.get("play_addr_h264", {}).get("url_list", []),
            video.get("download_addr", {}).get("url_list", []),
        ]

        for bit_rate in video.get("bit_rate", []):
            candidates.append(bit_rate.get("play_addr", {}).get("url_list", []))

        for url_list in candidates:
            for url in url_list:
                if url:
                    return url

        raise ValueError("No downloadable video URL found in the TikTok response.")

    @staticmethod
    def extract_cover_url(video_data: dict[str, Any]) -> Optional[str]:
        """提取封面图地址，按静态封面优先。"""
        video = video_data.get("video") or {}
        candidates = [
            video.get("cover", {}).get("url_list", []),
            video.get("origin_cover", {}).get("url_list", []),
            video.get("dynamic_cover", {}).get("url_list", []),
        ]

        for url_list in candidates:
            for url in url_list:
                if url:
                    return url

        return None

    @staticmethod
    def extract_author_name(video_data: dict[str, Any]) -> str:
        """提取作者标识并清洗成适合文件名的格式。"""
        author = video_data.get("author") or {}
        author_name = (
            author.get("unique_id")
            or author.get("nickname")
            or author.get("uid")
            or "unknown"
        )
        safe_author = re.sub(r"[^A-Za-z0-9_-]+", "_", str(author_name)).strip("_")
        return safe_author or "unknown"

    @staticmethod
    def extract_timestamp(video_data: dict[str, Any]) -> int:
        """提取创建时间戳，缺失时退回当前时间。"""
        raw_timestamp = video_data.get("create_time")
        if raw_timestamp is None:
            return int(time.time())

        try:
            return int(raw_timestamp)
        except (TypeError, ValueError):
            return int(time.time())

    @classmethod
    def extract_video_info(cls, video_data: dict[str, Any]) -> dict[str, Any]:
        """提取视频本身的信息，包括尺寸、封面和下载链接。"""
        video = video_data.get("video") or {}
        return {
            "aweme_id": video_data.get("aweme_id"),
            "desc": video_data.get("desc"),
            "create_time": cls.extract_timestamp(video_data),
            "duration_ms": video.get("duration"),
            "width": video.get("width"),
            "height": video.get("height"),
            "ratio": video.get("ratio"),
            "cover_url": cls.extract_cover_url(video_data),
            "download_url": cls.extract_download_url(video_data),
        }

    @classmethod
    def extract_tiktok_basic_info(cls, video_data: dict[str, Any]) -> dict[str, Any]:
        """提取作品在 TikTok 上的基础展示信息。"""
        author = video_data.get("author") or {}
        statistics = video_data.get("statistics") or {}
        music = video_data.get("music") or {}

        return {
            "author": cls.extract_author_name(video_data),
            "author_nickname": author.get("nickname"),
            "author_uid": author.get("uid"),
            "music_title": music.get("title"),
            "music_author": music.get("author"),
            "statistics": {
                "play_count": statistics.get("play_count"),
                "digg_count": statistics.get("digg_count"),
                "comment_count": statistics.get("comment_count"),
                "share_count": statistics.get("share_count"),
                "collect_count": statistics.get("collect_count"),
            },
        }

    @classmethod
    def extract_video_detail(cls, video_data: dict[str, Any]) -> dict[str, Any]:
        """组织接口返回的结构化视频结果。"""
        video_info = cls.extract_video_info(video_data)
        tiktok_basic_info = cls.extract_tiktok_basic_info(video_data)
        return {
            "aweme_id": video_info.get("aweme_id"),
            "download_url": video_info.get("download_url"),
            "video_info": video_info,
            "tiktok_basic_info": tiktok_basic_info,
        }

    async def fetch_video_info(self, value: str) -> dict[str, Any]:
        """返回统一的视频查询结果。"""
        video_data = await self.resolve_video_data(value)
        return self.extract_video_detail(video_data)
