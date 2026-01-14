"""
pytest配置和共享fixtures
"""

import pytest
import asyncio
from datetime import datetime
from tencent_video_scraper.models import ScraperConfig, VideoData, VideoURL, Comment


@pytest.fixture
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_config():
    """示例配置"""
    return ScraperConfig(
        rate_limit=2.0,
        timeout=30,
        max_retries=3,
        enable_comments=True,
        max_comments=50
    )


@pytest.fixture
def sample_video_url():
    """示例视频URL"""
    return VideoURL(
        quality="1080p",
        url="https://example.com/video.mp4",
        format="mp4",
        size=1024000,
        bitrate=2000
    )


@pytest.fixture
def sample_comment():
    """示例评论"""
    return Comment(
        content="这个视频很棒！",
        username="测试用户",
        publish_time=datetime.now(),
        likes=10,
        replies=2
    )


@pytest.fixture
def sample_video_data(sample_video_url, sample_comment):
    """示例视频数据"""
    return VideoData(
        url="https://v.qq.com/x/cover/test.html",
        title="测试视频",
        description="这是一个测试视频",
        duration=3600,
        view_count=10000,
        publish_time=datetime.now(),
        video_urls=[sample_video_url],
        comments=[sample_comment],
        is_svip=False,
        thumbnail_url="https://example.com/thumb.jpg",
        tags=["测试", "视频"]
    )