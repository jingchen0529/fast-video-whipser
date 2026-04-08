from urllib.parse import parse_qs, urlparse

import pytest

from app.crawlers.tiktok.crawler import TikTokAPPCrawler


def test_extract_aweme_id_from_numeric_value() -> None:
    assert TikTokAPPCrawler.extract_aweme_id_from_text("7339393672959757570") == "7339393672959757570"


def test_extract_aweme_id_from_video_url() -> None:
    url = "https://www.tiktok.com/@scout2015/video/6718335390845095173"
    assert TikTokAPPCrawler.extract_aweme_id_from_text(url) == "6718335390845095173"


def test_extract_download_url_prefers_play_addr() -> None:
    video_data = {
        "video": {
            "download_addr": {"url_list": ["https://download.example/video.mp4"]},
            "play_addr": {"url_list": ["https://play.example/video.mp4"]},
        }
    }
    assert TikTokAPPCrawler.extract_download_url(video_data) == "https://play.example/video.mp4"


def test_extract_download_url_falls_back_to_play_addr_h264() -> None:
    video_data = {
        "video": {
            "play_addr": {"url_list": []},
            "play_addr_h264": {"url_list": ["https://h264.example/video.mp4"]},
            "download_addr": {"url_list": ["https://download.example/video.mp4"]},
        }
    }
    assert TikTokAPPCrawler.extract_download_url(video_data) == "https://h264.example/video.mp4"


def test_extract_video_detail_groups_video_and_tiktok_basic_info() -> None:
    video_data = {
        "aweme_id": "1234567890",
        "desc": "demo video",
        "create_time": 1711888888,
        "author": {
            "unique_id": "angelinazhq",
            "nickname": "Angelina",
            "uid": "user-1",
        },
        "video": {
            "duration": 15000,
            "width": 720,
            "height": 1280,
            "ratio": "720p",
            "cover": {"url_list": ["https://example.com/cover.jpeg"]},
            "download_addr": {"url_list": ["https://example.com/video.mp4"]},
        },
        "music": {
            "title": "song",
            "author": "artist",
        },
        "statistics": {
            "play_count": 1,
            "digg_count": 2,
            "comment_count": 3,
            "share_count": 4,
            "collect_count": 5,
        },
    }

    detail = TikTokAPPCrawler.extract_video_detail(video_data)

    assert detail["aweme_id"] == "1234567890"
    assert detail["download_url"] == "https://example.com/video.mp4"
    assert detail["video_info"]["duration_ms"] == 15000
    assert detail["tiktok_basic_info"]["author"] == "angelinazhq"
    assert detail["tiktok_basic_info"]["statistics"]["collect_count"] == 5


@pytest.mark.asyncio
async def test_fetch_one_video_builds_feed_request_from_inline_params() -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def fetch_get_json(self, url: str) -> dict[str, object]:
            captured["url"] = url
            return {"aweme_list": [{"aweme_id": "1234567890"}]}

    crawler = TikTokAPPCrawler(http_client_factory=FakeClient)

    result = await crawler.fetch_one_video("1234567890")

    assert result["aweme_id"] == "1234567890"
    parsed_url = urlparse(str(captured["url"]))
    query = parse_qs(parsed_url.query)
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "api22-normal-c-alisg.tiktokv.com"
    assert parsed_url.path == "/aweme/v1/feed/"
    assert query["aweme_id"] == ["1234567890"]
    assert query["channel"] == ["googleplay"]
    assert query["app_name"] == ["musical_ly"]


@pytest.mark.asyncio
async def test_fetch_video_info_returns_structured_detail() -> None:
    async def fake_resolve_video_data(self, value: str) -> dict[str, object]:
        assert value == "1234567890"
        return {
            "aweme_id": "1234567890",
            "desc": "demo video",
            "create_time": 1711888888,
            "author": {
                "unique_id": "angelinazhq",
                "nickname": "Angelina",
                "uid": "user-1",
            },
            "video": {
                "duration": 15000,
                "width": 720,
                "height": 1280,
                "ratio": "720p",
                "cover": {"url_list": ["https://example.com/cover.jpeg"]},
                "download_addr": {"url_list": ["https://example.com/video.mp4"]},
            },
            "music": {
                "title": "song",
                "author": "artist",
            },
            "statistics": {
                "play_count": 1,
                "digg_count": 2,
                "comment_count": 3,
                "share_count": 4,
                "collect_count": 5,
            },
        }

    crawler = TikTokAPPCrawler()
    crawler.resolve_video_data = fake_resolve_video_data.__get__(crawler, TikTokAPPCrawler)

    result = await crawler.fetch_video_info("1234567890")

    assert result["aweme_id"] == "1234567890"
    assert result["download_url"] == "https://example.com/video.mp4"
    assert result["video_info"]["duration_ms"] == 15000
    assert result["tiktok_basic_info"]["statistics"]["collect_count"] == 5
