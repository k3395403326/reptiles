"""
数据模型属性测试

测试数据模型的JSON序列化完整性和其他属性。
Feature: tencent-video-scraper, Property 5: JSON序列化完整性
"""

import pytest
import json
from datetime import datetime
from hypothesis import given, strategies as st
from hypothesis import settings

from tencent_video_scraper.models import (
    VideoData, VideoURL, Comment, ScraperConfig, BatchReport
)


# 自定义策略
@st.composite
def video_url_strategy(draw):
    """生成VideoURL实例的策略"""
    quality = draw(st.sampled_from(['1080p', '720p', '480p', '360p', '240p']))
    url = draw(st.text(min_size=10, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    format_type = draw(st.sampled_from(['mp4', 'm3u8', 'flv', 'avi']))
    size = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=10**9)))
    bitrate = draw(st.one_of(st.none(), st.integers(min_value=100, max_value=50000)))
    
    return VideoURL(
        quality=quality,
        url=f"http://example.com/{url}",
        format=format_type,
        size=size,
        bitrate=bitrate
    )


@st.composite
def comment_strategy(draw):
    """生成Comment实例的策略"""
    content = draw(st.text(min_size=1, max_size=500, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    username = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    publish_time = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2024, 12, 31)
    ))
    likes = draw(st.integers(min_value=0, max_value=100000))
    replies = draw(st.integers(min_value=0, max_value=1000))
    
    return Comment(
        content=content,
        username=username,
        publish_time=publish_time,
        likes=likes,
        replies=replies
    )


@st.composite
def video_data_strategy(draw):
    """生成VideoData实例的策略"""
    url_suffix = draw(st.text(min_size=5, max_size=50, alphabet=st.characters(min_codepoint=97, max_codepoint=122)))
    url = f"https://v.qq.com/x/cover/{url_suffix}.html"
    title = draw(st.text(min_size=1, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    description = draw(st.text(min_size=0, max_size=1000, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    duration = draw(st.integers(min_value=1, max_value=86400))  # 1秒到24小时
    view_count = draw(st.integers(min_value=0, max_value=10**9))
    publish_time = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2024, 12, 31)
    ))
    video_urls = draw(st.lists(video_url_strategy(), min_size=0, max_size=10))
    comments = draw(st.lists(comment_strategy(), min_size=0, max_size=20))
    is_svip = draw(st.booleans())
    thumbnail_url = draw(st.text(min_size=0, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    tags = draw(st.lists(st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)), min_size=0, max_size=20))
    
    return VideoData(
        url=url,
        title=title,
        description=description,
        duration=duration,
        view_count=view_count,
        publish_time=publish_time,
        video_urls=video_urls,
        comments=comments,
        is_svip=is_svip,
        thumbnail_url=thumbnail_url,
        tags=tags
    )


@st.composite
def scraper_config_strategy(draw):
    """生成ScraperConfig实例的策略"""
    rate_limit = draw(st.floats(min_value=0.1, max_value=10.0))
    timeout = draw(st.integers(min_value=5, max_value=300))
    max_retries = draw(st.integers(min_value=0, max_value=10))
    output_format = draw(st.sampled_from(['json', 'csv', 'xml']))
    enable_comments = draw(st.booleans())
    max_comments = draw(st.integers(min_value=1, max_value=1000))
    proxies = draw(st.lists(st.text(min_size=5, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126)), min_size=0, max_size=10))
    user_agents = draw(st.lists(st.text(min_size=10, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)), min_size=0, max_size=10))
    enable_download = draw(st.booleans())
    download_path = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    enable_detailed_logs = draw(st.booleans())
    error_threshold = draw(st.integers(min_value=1, max_value=100))
    
    return ScraperConfig(
        rate_limit=rate_limit,
        timeout=timeout,
        max_retries=max_retries,
        output_format=output_format,
        enable_comments=enable_comments,
        max_comments=max_comments,
        proxies=proxies,
        user_agents=user_agents,
        enable_download=enable_download,
        download_path=download_path,
        enable_detailed_logs=enable_detailed_logs,
        error_threshold=error_threshold
    )


class TestJSONSerializationIntegrity:
    """测试JSON序列化完整性"""
    
    @given(video_url_strategy())
    @settings(max_examples=100)
    def test_video_url_json_roundtrip(self, video_url):
        """
        测试VideoURL的JSON序列化往返一致性
        Feature: tencent-video-scraper, Property 5: JSON序列化完整性
        """
        # 序列化为字典
        data_dict = video_url.to_dict()
        
        # 验证字典包含所有必要字段
        assert 'quality' in data_dict
        assert 'url' in data_dict
        assert 'format' in data_dict
        assert data_dict['quality'] == video_url.quality
        assert data_dict['url'] == video_url.url
        assert data_dict['format'] == video_url.format
        
        # 验证可选字段
        if video_url.size is not None:
            assert data_dict['size'] == video_url.size
        if video_url.bitrate is not None:
            assert data_dict['bitrate'] == video_url.bitrate
    
    @given(comment_strategy())
    @settings(max_examples=100)
    def test_comment_json_roundtrip(self, comment):
        """
        测试Comment的JSON序列化往返一致性
        Feature: tencent-video-scraper, Property 5: JSON序列化完整性
        """
        # 序列化为字典
        data_dict = comment.to_dict()
        
        # 验证所有字段都存在且正确
        assert data_dict['content'] == comment.content
        assert data_dict['username'] == comment.username
        assert data_dict['publish_time'] == comment.publish_time.isoformat()
        assert data_dict['likes'] == comment.likes
        assert data_dict['replies'] == comment.replies
        
        # 验证时间格式正确
        parsed_time = datetime.fromisoformat(data_dict['publish_time'])
        assert parsed_time == comment.publish_time
    
    @given(video_data_strategy())
    @settings(max_examples=100)
    def test_video_data_json_roundtrip(self, video_data):
        """
        测试VideoData的JSON序列化往返一致性
        Feature: tencent-video-scraper, Property 5: JSON序列化完整性
        """
        # 序列化为JSON字符串
        json_str = video_data.to_json()
        
        # 验证JSON格式有效
        parsed_data = json.loads(json_str)
        
        # 验证所有字段都存在
        required_fields = [
            'url', 'title', 'description', 'duration', 'view_count',
            'publish_time', 'video_urls', 'comments', 'is_svip',
            'thumbnail_url', 'tags'
        ]
        
        for field in required_fields:
            assert field in parsed_data
        
        # 验证基本字段值
        assert parsed_data['url'] == video_data.url
        assert parsed_data['title'] == video_data.title
        assert parsed_data['description'] == video_data.description
        assert parsed_data['duration'] == video_data.duration
        assert parsed_data['view_count'] == video_data.view_count
        assert parsed_data['is_svip'] == video_data.is_svip
        assert parsed_data['thumbnail_url'] == video_data.thumbnail_url
        assert parsed_data['tags'] == video_data.tags
        
        # 验证时间格式
        parsed_time = datetime.fromisoformat(parsed_data['publish_time'])
        assert parsed_time == video_data.publish_time
        
        # 验证嵌套对象数量
        assert len(parsed_data['video_urls']) == len(video_data.video_urls)
        assert len(parsed_data['comments']) == len(video_data.comments)
        
        # 完整往返测试
        reconstructed = VideoData.from_dict(parsed_data)
        assert reconstructed.url == video_data.url
        assert reconstructed.title == video_data.title
        assert reconstructed.duration == video_data.duration
        assert reconstructed.is_svip == video_data.is_svip
    
    @given(scraper_config_strategy())
    @settings(max_examples=100)
    def test_scraper_config_json_roundtrip(self, config):
        """
        测试ScraperConfig的JSON序列化往返一致性
        Feature: tencent-video-scraper, Property 5: JSON序列化完整性
        """
        # 序列化为JSON字符串
        json_str = config.to_json()
        
        # 验证JSON格式有效
        parsed_data = json.loads(json_str)
        
        # 验证所有字段都存在
        config_dict = config.to_dict()
        for key, value in config_dict.items():
            assert key in parsed_data
            assert parsed_data[key] == value
        
        # 完整往返测试
        reconstructed = ScraperConfig.from_json(json_str)
        assert reconstructed.rate_limit == config.rate_limit
        assert reconstructed.timeout == config.timeout
        assert reconstructed.max_retries == config.max_retries
        assert reconstructed.output_format == config.output_format
        assert reconstructed.enable_comments == config.enable_comments
        assert reconstructed.max_comments == config.max_comments
        assert reconstructed.proxies == config.proxies
        assert reconstructed.user_agents == config.user_agents
        assert reconstructed.enable_download == config.enable_download
        assert reconstructed.download_path == config.download_path
        assert reconstructed.enable_detailed_logs == config.enable_detailed_logs
        assert reconstructed.error_threshold == config.error_threshold


class TestDataModelProperties:
    """测试数据模型的其他属性"""
    
    @given(video_data_strategy())
    @settings(max_examples=50)
    def test_video_data_consistency(self, video_data):
        """
        测试VideoData的数据一致性
        """
        # 基本字段不应为None（除了可选字段）
        assert video_data.url is not None
        assert video_data.title is not None
        assert video_data.duration >= 0
        assert video_data.view_count >= 0
        assert isinstance(video_data.video_urls, list)
        assert isinstance(video_data.comments, list)
        assert isinstance(video_data.is_svip, bool)
        assert isinstance(video_data.tags, list)
    
    @given(scraper_config_strategy())
    @settings(max_examples=50)
    def test_scraper_config_constraints(self, config):
        """
        测试ScraperConfig的约束条件
        """
        # 数值约束
        assert config.rate_limit > 0
        assert config.timeout > 0
        assert config.max_retries >= 0
        assert config.max_comments > 0
        assert config.error_threshold > 0
        
        # 格式约束
        assert config.output_format in ['json', 'csv', 'xml']
        
        # 列表类型约束
        assert isinstance(config.proxies, list)
        assert isinstance(config.user_agents, list)
    
    def test_batch_report_calculation(self):
        """
        测试BatchReport的计算属性
        """
        from datetime import timedelta
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=10)
        
        report = BatchReport(
            total_urls=10,
            successful_count=8,
            failed_count=2,
            failed_urls=['url1', 'url2'],
            start_time=start_time,
            end_time=end_time,
            total_duration=10.0
        )
        
        report_dict = report.to_dict()
        
        # 验证成功率计算
        assert report_dict['success_rate'] == 0.8
        assert report_dict['total_urls'] == 10
        assert report_dict['successful_count'] == 8
        assert report_dict['failed_count'] == 2
        assert len(report_dict['failed_urls']) == 2