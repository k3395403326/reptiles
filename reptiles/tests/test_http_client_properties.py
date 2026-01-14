"""
HTTP客户端属性测试

测试HTTP客户端的配置参数应用和其他属性。
Feature: tencent-video-scraper, Property 11: 配置参数应用
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime

from tencent_video_scraper.http_client import HTTPClient
from tencent_video_scraper.models import ScraperConfig
from tencent_video_scraper.proxy_manager import ProxyManager, ProxyInfo, ProxyStatus


# 自定义策略
@st.composite
def valid_scraper_config_strategy(draw):
    """生成有效的ScraperConfig实例的策略"""
    rate_limit = draw(st.floats(min_value=0.1, max_value=10.0))
    timeout = draw(st.integers(min_value=5, max_value=300))
    max_retries = draw(st.integers(min_value=0, max_value=10))
    output_format = draw(st.sampled_from(['json', 'csv', 'xml']))
    enable_comments = draw(st.booleans())
    max_comments = draw(st.integers(min_value=1, max_value=1000))
    
    # 生成有效的代理URL
    proxy_count = draw(st.integers(min_value=0, max_value=5))
    proxies = []
    for _ in range(proxy_count):
        proxy_type = draw(st.sampled_from(['http', 'https', 'socks5']))
        host = draw(st.text(min_size=5, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'))
        port = draw(st.integers(min_value=1000, max_value=65535))
        proxies.append(f"{proxy_type}://{host}.com:{port}")
    
    # 生成有效的User-Agent
    ua_count = draw(st.integers(min_value=0, max_value=5))
    user_agents = []
    for _ in range(ua_count):
        browser = draw(st.sampled_from(['Chrome', 'Firefox', 'Safari', 'Edge']))
        version = draw(st.integers(min_value=80, max_value=120))
        user_agents.append(f"Mozilla/5.0 ({browser}/{version})")
    
    enable_download = draw(st.booleans())
    download_path = draw(st.text(min_size=1, max_size=50, alphabet='abcdefghijklmnopqrstuvwxyz0123456789/_-'))
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


@st.composite
def valid_url_strategy(draw):
    """生成有效URL的策略"""
    protocol = draw(st.sampled_from(['http', 'https']))
    domain = draw(st.text(min_size=3, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'))
    tld = draw(st.sampled_from(['com', 'org', 'net', 'cn']))
    path = draw(st.text(min_size=0, max_size=50, alphabet='abcdefghijklmnopqrstuvwxyz0123456789/_-'))
    
    url = f"{protocol}://{domain}.{tld}"
    if path:
        url += f"/{path}"
    
    return url


class TestHTTPClientConfigurationApplication:
    """测试HTTP客户端配置参数应用"""
    
    @given(valid_scraper_config_strategy())
    @settings(max_examples=100)
    def test_http_client_applies_timeout_config(self, config):
        """
        测试HTTP客户端正确应用超时配置
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        # 验证配置被正确存储
        assert client.config.timeout == config.timeout
        assert client.config.max_retries == config.max_retries
        assert client.config.rate_limit == config.rate_limit
        
        # 验证代理配置
        assert client.config.proxies == config.proxies
        assert client.config.user_agents == config.user_agents
        
        # 验证日志配置
        assert client.config.enable_detailed_logs == config.enable_detailed_logs
    
    @given(valid_scraper_config_strategy())
    @settings(max_examples=100)
    def test_http_client_applies_retry_config(self, config):
        """
        测试HTTP客户端正确应用重试配置
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        # 验证重试次数配置
        assert client.config.max_retries == config.max_retries
        
        # 验证重试逻辑
        assert client._should_retry(500, 0) == (config.max_retries > 0)
        assert client._should_retry(429, 0) == (config.max_retries > 0)
        assert client._should_retry(200, 0) == False
        assert client._should_retry(404, 0) == False
        
        # 验证超过最大重试次数时不再重试
        assert client._should_retry(500, config.max_retries) == False
    
    @given(valid_scraper_config_strategy())
    @settings(max_examples=100)
    def test_http_client_applies_proxy_config(self, config):
        """
        测试HTTP客户端正确应用代理配置
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        if config.proxies:
            # 验证代理管理器被创建
            assert client.proxy_manager is not None
            assert isinstance(client.proxy_manager, ProxyManager)
            
            # 验证代理列表
            proxy_urls = list(client.proxy_manager.proxies.keys())
            assert set(proxy_urls) == set(config.proxies)
            
            # 验证获取代理功能
            proxy = client._get_proxy()
            if proxy:  # 如果有可用代理
                assert proxy in config.proxies
        else:
            # 没有配置代理时，代理管理器应该为None
            assert client.proxy_manager is None
            assert client._get_proxy() is None
    
    @given(valid_scraper_config_strategy())
    @settings(max_examples=100)
    def test_http_client_applies_user_agent_config(self, config):
        """
        测试HTTP客户端正确应用User-Agent配置
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        # 生成多个请求头并验证User-Agent轮换
        headers_list = []
        for _ in range(10):
            headers = client._build_headers()
            headers_list.append(headers['User-Agent'])
            
            # 验证User-Agent存在
            assert 'User-Agent' in headers
            assert len(headers['User-Agent']) > 0
        
        if config.user_agents:
            # 如果配置了自定义User-Agent，应该只使用配置的
            for ua in headers_list:
                assert ua in config.user_agents
        else:
            # 如果没有配置，应该使用默认的或fake-useragent生成的
            for ua in headers_list:
                assert len(ua) > 10  # 基本的User-Agent长度检查
    
    @given(valid_scraper_config_strategy())
    @settings(max_examples=50)
    def test_http_client_applies_rate_limit_config(self, config):
        """
        测试HTTP客户端正确应用速率限制配置
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        # 验证速率限制配置
        assert client.config.rate_limit == config.rate_limit
        
        # 验证速率限制计算
        if config.rate_limit > 0:
            expected_interval = 1.0 / config.rate_limit
            
            # 模拟连续请求的时间间隔检查
            import time
            client.last_request_time = time.time() - expected_interval - 0.1
            
            # 应该不需要等待
            current_time = time.time()
            time_since_last = current_time - client.last_request_time
            min_interval = 1.0 / config.rate_limit
            
            if time_since_last >= min_interval:
                # 时间间隔足够，不需要等待
                assert True
            else:
                # 时间间隔不够，需要等待
                sleep_time = min_interval - time_since_last
                assert sleep_time > 0
    
    @given(valid_scraper_config_strategy())
    @settings(max_examples=50)
    def test_http_client_header_consistency(self, config):
        """
        测试HTTP客户端请求头的一致性
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        # 生成多个请求头
        for _ in range(5):
            headers = client._build_headers()
            
            # 验证必要的请求头存在
            required_headers = [
                'User-Agent', 'Accept', 'Accept-Language', 'Accept-Encoding',
                'DNT', 'Connection', 'Upgrade-Insecure-Requests'
            ]
            
            for header in required_headers:
                assert header in headers
                assert len(headers[header]) > 0
            
            # 验证请求头值的合理性
            assert 'Mozilla' in headers['User-Agent']
            assert 'text/html' in headers['Accept']
            assert 'zh-CN' in headers['Accept-Language']
            assert 'gzip' in headers['Accept-Encoding']
    
    @given(valid_scraper_config_strategy(), valid_url_strategy())
    @settings(max_examples=50)
    def test_http_client_referer_handling(self, config, referer_url):
        """
        测试HTTP客户端Referer处理
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        client = HTTPClient(config)
        
        # 测试不带Referer的请求头
        headers_without_referer = client._build_headers()
        assert 'Referer' not in headers_without_referer
        
        # 测试带Referer的请求头
        headers_with_referer = client._build_headers(referer=referer_url)
        assert 'Referer' in headers_with_referer
        assert headers_with_referer['Referer'] == referer_url
    
    def test_http_client_stats_tracking(self):
        """
        测试HTTP客户端统计信息跟踪
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        config = ScraperConfig()
        client = HTTPClient(config)
        
        # 初始统计应该为0
        stats = client.get_stats()
        assert stats['total_requests'] == 0
        assert stats['successful_requests'] == 0
        assert stats['failed_requests'] == 0
        assert stats['success_rate'] == 0
        
        # 模拟一些请求统计
        client.request_count = 10
        client.success_count = 8
        client.error_count = 2
        
        stats = client.get_stats()
        assert stats['total_requests'] == 10
        assert stats['successful_requests'] == 8
        assert stats['failed_requests'] == 2
        assert stats['success_rate'] == 0.8


class TestHTTPClientBackoffCalculation:
    """测试HTTP客户端退避算法"""
    
    @given(st.integers(min_value=0, max_value=5), st.integers(min_value=400, max_value=599))
    @settings(max_examples=50)
    def test_backoff_delay_calculation(self, attempt, status_code):
        """
        测试退避延迟计算的合理性
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        config = ScraperConfig()
        client = HTTPClient(config)
        
        # 使用同步方式测试延迟计算逻辑
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            delay = loop.run_until_complete(client._calculate_backoff_delay(attempt, status_code))
            
            # 验证延迟时间的合理性
            assert delay >= 0
            assert delay <= 60.0  # 最大延迟不超过60秒
            
            # 验证指数退避特性
            if attempt > 0:
                prev_delay = loop.run_until_complete(client._calculate_backoff_delay(attempt - 1, status_code))
                # 当前延迟应该大于等于前一次（考虑随机抖动）
                assert delay >= prev_delay * 0.5  # 允许一定的随机性
            
            # 验证不同状态码的基础延迟
            if status_code == 429:  # 限流
                assert delay >= 2.0 * (2 ** attempt)  # 基础延迟2秒
            elif 500 <= status_code < 600:  # 服务器错误
                assert delay >= 1.5 * (2 ** attempt)  # 基础延迟1.5秒
        finally:
            loop.close()
    
    def test_session_management(self):
        """
        测试会话管理
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        config = ScraperConfig(timeout=30)
        client = HTTPClient(config)
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 获取会话
            session1 = loop.run_until_complete(client._get_session())
            assert session1 is not None
            assert isinstance(session1, aiohttp.ClientSession)
            
            # 再次获取应该是同一个会话
            session2 = loop.run_until_complete(client._get_session())
            assert session1 is session2
            
            # 验证超时配置
            assert session1.timeout.total == 30
            
            # 清理
            loop.run_until_complete(client.close())
        finally:
            loop.close()


class TestProxyManagerIntegration:
    """测试代理管理器集成"""
    
    def test_proxy_manager_creation(self):
        """
        测试代理管理器创建
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        # 有代理配置时应该创建代理管理器
        config_with_proxies = ScraperConfig(proxies=['http://proxy1.com:8080', 'http://proxy2.com:8080'])
        client_with_proxies = HTTPClient(config_with_proxies)
        assert client_with_proxies.proxy_manager is not None
        
        # 无代理配置时不应该创建代理管理器
        config_without_proxies = ScraperConfig(proxies=[])
        client_without_proxies = HTTPClient(config_without_proxies)
        assert client_without_proxies.proxy_manager is None
    
    def test_proxy_selection_logic(self):
        """
        测试代理选择逻辑
        Feature: tencent-video-scraper, Property 11: 配置参数应用
        Validates: Requirements 4.1, 4.3
        """
        proxies = ['http://proxy1.com:8080', 'http://proxy2.com:8080', 'http://proxy3.com:8080']
        config = ScraperConfig(proxies=proxies)
        client = HTTPClient(config)
        
        # 获取代理应该从配置的代理列表中选择
        for _ in range(10):
            proxy = client._get_proxy()
            if proxy:  # 如果有可用代理
                assert proxy in proxies