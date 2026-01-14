"""
Web服务属性测试

测试Web API响应格式。
Feature: tencent-video-scraper, Property 28: Web API响应格式
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from hypothesis import given, strategies as st, settings

from tencent_video_scraper.web_service import WebService, create_app
from tencent_video_scraper.models import ScraperConfig


class TestWebAPIResponseFormat:
    """
    测试Web API响应格式
    Property 28: Web API响应格式
    Validates: Requirements 10.2, 10.5
    """
    
    def setup_method(self):
        """设置测试环境"""
        self.service = WebService()
        self.app = self.service.app
        self.client = self.app.test_client()
    
    def test_api_parse_returns_required_fields(self):
        """
        测试API返回必需字段
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2, 10.5**
        """
        # 测试空URL
        response = self.client.post('/api/parse', 
            data=json.dumps({'url': ''}),
            content_type='application/json'
        )
        
        data = json.loads(response.data)
        
        # 验证必需字段存在
        assert 'success' in data, "响应应该包含success字段"
        assert 'play_url' in data, "响应应该包含play_url字段"
        assert 'share_url' in data, "响应应该包含share_url字段"
        
        # 验证success是布尔值
        assert isinstance(data['success'], bool), "success应该是布尔值"
    
    @given(
        video_id=st.text(min_size=8, max_size=16, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd')))
    )
    @settings(max_examples=20, deadline=30000)
    def test_api_parse_with_valid_url_format(self, video_id):
        """
        测试有效URL格式的API响应
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2, 10.5**
        """
        # 构建腾讯视频URL
        video_url = f"https://v.qq.com/x/cover/{video_id}.html"
        
        # Mock解析方法以避免实际网络请求
        with patch.object(self.service, '_parse_video_sync', return_value={
            'success': True,
            'video_url': video_url,
            'play_url': 'https://example.com/video.m3u8',
            'share_url': '/share/abc123',
            'quality': '1080p',
            'format': 'm3u8',
            'error': None
        }):
            response = self.client.post('/api/parse',
                data=json.dumps({'url': video_url}),
                content_type='application/json'
            )
            
            data = json.loads(response.data)
            
            # 验证响应格式
            assert 'success' in data, "响应应该包含success字段"
            assert 'video_url' in data, "响应应该包含video_url字段"
            assert 'play_url' in data, "响应应该包含play_url字段"
            assert 'share_url' in data, "响应应该包含share_url字段"
            
            # 如果成功，验证URL格式
            if data['success']:
                assert data['play_url'] is not None, "成功时play_url不应为None"
                assert data['share_url'] is not None, "成功时share_url不应为None"
                assert data['play_url'].startswith('http'), "play_url应该是有效的HTTP URL"
    
    def test_api_parse_with_invalid_url(self):
        """
        测试无效URL的API响应
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        # 测试非腾讯视频URL
        response = self.client.post('/api/parse',
            data=json.dumps({'url': 'https://example.com/video'}),
            content_type='application/json'
        )
        
        data = json.loads(response.data)
        
        # 应该返回失败
        assert data['success'] == False, "无效URL应该返回失败"
        assert 'error' in data, "失败时应该包含error字段"
        assert data['error'] is not None, "error不应为None"
    
    def test_api_parse_get_method(self):
        """
        测试GET方法的API响应
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        video_url = "https://v.qq.com/x/cover/test123.html"
        
        # Mock解析方法以避免实际网络请求
        with patch.object(self.service, '_parse_video_sync', return_value={
            'success': True,
            'video_url': video_url,
            'play_url': 'https://example.com/video.m3u8',
            'share_url': '/share/abc123',
            'quality': '720p',
            'format': 'm3u8',
            'error': None
        }):
            response = self.client.get(f'/api/parse?url={video_url}')
            
            data = json.loads(response.data)
            
            # 验证响应格式
            assert 'success' in data, "GET请求响应应该包含success字段"
            assert 'play_url' in data, "GET请求响应应该包含play_url字段"
            assert 'share_url' in data, "GET请求响应应该包含share_url字段"
    
    def test_api_health_endpoint(self):
        """
        测试健康检查端点
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        response = self.client.get('/api/health')
        
        data = json.loads(response.data)
        
        assert 'status' in data, "健康检查应该返回status字段"
        assert data['status'] == 'ok', "健康状态应该是ok"
        assert 'timestamp' in data, "健康检查应该返回timestamp字段"
    
    @given(
        error_message=st.text(min_size=1, max_size=100)
    )
    @settings(max_examples=20, deadline=5000)
    def test_error_response_format(self, error_message):
        """
        测试错误响应格式
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        # 测试空请求
        response = self.client.post('/api/parse',
            data=json.dumps({}),
            content_type='application/json'
        )
        
        data = json.loads(response.data)
        
        # 验证错误响应格式
        assert data['success'] == False, "错误时success应该为False"
        assert 'error' in data, "错误响应应该包含error字段"
        assert data['play_url'] is None, "错误时play_url应该为None"
        assert data['share_url'] is None, "错误时share_url应该为None"


class TestWebServiceFunctionality:
    """测试Web服务功能"""
    
    def setup_method(self):
        """设置测试环境"""
        self.service = WebService()
        self.app = self.service.app
        self.client = self.app.test_client()
    
    def test_index_page_loads(self):
        """
        测试首页加载
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        response = self.client.get('/')
        
        assert response.status_code == 200, "首页应该返回200"
        assert b'<!DOCTYPE html>' in response.data, "首页应该返回HTML"
        assert '腾讯视频解析'.encode('utf-8') in response.data, "首页应该包含标题"
    
    def test_play_page_requires_url(self):
        """
        测试播放页面需要URL参数
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        response = self.client.get('/play')
        
        assert response.status_code == 400, "缺少URL参数应该返回400"
    
    def test_play_page_with_url(self):
        """
        测试播放页面带URL参数
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        play_url = "https://example.com/video.m3u8"
        response = self.client.get(f'/play?url={play_url}&title=测试视频')
        
        assert response.status_code == 200, "播放页面应该返回200"
        assert b'<video' in response.data, "播放页面应该包含video标签"
    
    def test_share_page_not_found(self):
        """
        测试不存在的分享页面
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.5**
        """
        response = self.client.get('/share/nonexistent123')
        
        assert response.status_code == 404, "不存在的分享链接应该返回404"
    
    def test_cache_functionality(self):
        """
        测试缓存功能
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        # 测试缓存键生成
        url1 = "https://v.qq.com/x/cover/test1.html"
        url2 = "https://v.qq.com/x/cover/test2.html"
        
        key1 = self.service._get_cache_key(url1)
        key2 = self.service._get_cache_key(url2)
        
        assert key1 != key2, "不同URL应该生成不同的缓存键"
        
        # 相同URL应该生成相同的缓存键
        key1_again = self.service._get_cache_key(url1)
        assert key1 == key1_again, "相同URL应该生成相同的缓存键"
    
    def test_quality_detection(self):
        """
        测试画质检测
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        # 测试1080p检测
        assert self.service._detect_quality("https://example.com/1080p/video.m3u8") == "1080p"
        assert self.service._detect_quality("https://example.com/fhd/video.m3u8") == "1080p"
        
        # 测试720p检测
        assert self.service._detect_quality("https://example.com/720p/video.m3u8") == "720p"
        assert self.service._detect_quality("https://example.com/hd/video.m3u8") == "720p"
        
        # 测试480p检测
        assert self.service._detect_quality("https://example.com/480p/video.m3u8") == "480p"
        assert self.service._detect_quality("https://example.com/sd/video.m3u8") == "480p"
        
        # 测试未知画质
        assert self.service._detect_quality("https://example.com/video.m3u8") == "unknown"
    
    def test_format_detection(self):
        """
        测试格式检测
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        assert self.service._detect_format("https://example.com/video.m3u8") == "m3u8"
        assert self.service._detect_format("https://example.com/video.mp4") == "mp4"
        assert self.service._detect_format("https://example.com/video.flv") == "flv"
        assert self.service._detect_format("https://example.com/video") == "unknown"


class TestCreateAppFactory:
    """测试应用工厂函数"""
    
    def test_create_app_returns_flask_app(self):
        """
        测试create_app返回Flask应用
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        from flask import Flask
        
        app = create_app()
        
        assert isinstance(app, Flask), "create_app应该返回Flask应用"
    
    def test_create_app_with_config(self):
        """
        测试create_app接受配置
        Feature: tencent-video-scraper, Property 28: Web API响应格式
        **Validates: Requirements 10.2**
        """
        config = ScraperConfig(timeout=60, max_retries=5)
        
        app = create_app(config)
        
        assert app is not None, "create_app应该成功创建应用"
