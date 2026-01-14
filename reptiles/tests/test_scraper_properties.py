"""
爬虫引擎属性测试

测试错误处理一致性和批量处理鲁棒性。
Feature: tencent-video-scraper, Property 4: 错误处理一致性
Feature: tencent-video-scraper, Property 6: 批量处理鲁棒性
Feature: tencent-video-scraper, Property 8: 批量任务报告生成
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from hypothesis import given, strategies as st, settings
from datetime import datetime

from tencent_video_scraper.scraper import ScraperEngine, AdvancedScraperEngine
from tencent_video_scraper.models import ScraperConfig, VideoData, VideoURL


def run_async(coro):
    """运行异步协程的辅助函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestErrorHandlingConsistency:
    """测试错误处理一致性"""
    
    @given(
        error_type=st.sampled_from(['network', 'parsing', 'svip', 'validation']),
        url=st.text(min_size=10, max_size=50).filter(lambda x: x.strip())
    )
    @settings(max_examples=30, deadline=5000)
    def test_error_handling_returns_clear_message(self, error_type, url):
        """
        测试错误处理返回明确的错误信息
        Feature: tencent-video-scraper, Property 4: 错误处理一致性
        """
        async def _test():
            config = ScraperConfig()
            engine = ScraperEngine(config)
            
            # 模拟不同类型的错误
            if error_type == 'network':
                engine.http_client.get = AsyncMock(side_effect=ConnectionError("网络连接失败"))
            elif error_type == 'parsing':
                engine.http_client.get = AsyncMock(return_value=Mock(
                    status=200,
                    text=AsyncMock(return_value="<html><body>无效内容</body></html>")
                ))
            elif error_type == 'svip':
                engine.http_client.get = AsyncMock(return_value=Mock(
                    status=403,
                    text=AsyncMock(return_value="SVIP专享内容")
                ))
            else:  # validation
                engine.http_client.get = AsyncMock(return_value=Mock(
                    status=200,
                    text=AsyncMock(return_value="")
                ))
            
            test_url = f"https://v.qq.com/x/cover/{url}.html"
            
            # 执行爬取，应该抛出异常但不崩溃
            with pytest.raises(Exception) as exc_info:
                await engine.scrape_video(test_url)
            
            # 验证错误信息
            error_message = str(exc_info.value)
            assert len(error_message) > 0, "错误信息不能为空"
            
            # 验证统计信息更新
            stats = engine.get_stats()
            assert stats['failed_videos'] > 0, "应该记录失败的视频数"
            assert len(stats['errors']) > 0, "应该记录错误详情"
            
            # 验证错误详情包含必要信息
            error_detail = stats['errors'][0]
            assert 'url' in error_detail, "错误详情应该包含URL"
            assert 'error' in error_detail, "错误详情应该包含错误信息"
            assert 'timestamp' in error_detail, "错误详情应该包含时间戳"
        
        run_async(_test())
    
    @given(
        invalid_url_type=st.sampled_from(['empty', 'malformed', 'wrong_domain', 'missing_protocol'])
    )
    @settings(max_examples=20, deadline=5000)
    def test_invalid_url_handling(self, invalid_url_type):
        """
        测试无效URL的处理
        Feature: tencent-video-scraper, Property 4: 错误处理一致性
        """
        async def _test():
            config = ScraperConfig()
            engine = ScraperEngine(config)
            
            # 模拟HTTP客户端
            engine.http_client.get = AsyncMock(side_effect=Exception("无效URL"))
            
            # 生成不同类型的无效URL
            if invalid_url_type == 'empty':
                test_url = ""
            elif invalid_url_type == 'malformed':
                test_url = "not-a-valid-url"
            elif invalid_url_type == 'wrong_domain':
                test_url = "https://example.com/video.html"
            else:  # missing_protocol
                test_url = "v.qq.com/x/cover/test.html"
            
            # 执行爬取，应该抛出异常
            with pytest.raises(Exception):
                await engine.scrape_video(test_url)
            
            # 验证统计信息
            stats = engine.get_stats()
            assert stats['total_videos'] > 0, "应该记录尝试的视频数"
            assert stats['failed_videos'] > 0, "应该记录失败的视频数"
        
        run_async(_test())
    
    def test_engine_does_not_crash_on_error(self):
        """
        测试引擎在错误时不会崩溃
        Feature: tencent-video-scraper, Property 4: 错误处理一致性
        """
        async def _test():
            config = ScraperConfig()
            engine = ScraperEngine(config)
            
            # 模拟各种错误
            engine.http_client.get = AsyncMock(side_effect=Exception("测试错误"))
            
            # 多次尝试爬取，引擎不应该崩溃
            for i in range(3):
                try:
                    await engine.scrape_video(f"https://v.qq.com/test{i}.html")
                except Exception:
                    pass  # 预期会抛出异常
            
            # 验证引擎仍然可用
            stats = engine.get_stats()
            assert stats['total_videos'] == 3, "应该记录所有尝试"
            assert stats['failed_videos'] == 3, "应该记录所有失败"
            
            # 验证可以重置统计
            engine.reset_stats()
            stats = engine.get_stats()
            assert stats['total_videos'] == 0, "重置后统计应该为0"
        
        run_async(_test())


class TestBatchProcessingRobustness:
    """测试批量处理鲁棒性"""
    
    @given(
        url_count=st.integers(min_value=1, max_value=5),
        failure_indices=st.lists(st.integers(min_value=0, max_value=4), max_size=3)
    )
    @settings(max_examples=20, deadline=10000)
    def test_batch_continues_after_failure(self, url_count, failure_indices):
        """
        测试批量处理在某个URL失败后继续处理剩余URL
        Feature: tencent-video-scraper, Property 6: 批量处理鲁棒性
        """
        async def _test():
            config = ScraperConfig()
            engine = ScraperEngine(config)
            
            # 确保失败索引在范围内
            valid_failure_indices = [i for i in failure_indices if i < url_count]
            
            # 生成测试URL列表
            urls = [f"https://v.qq.com/x/cover/test{i}.html" for i in range(url_count)]
            
            # 模拟部分URL失败
            async def mock_get(url, **kwargs):
                # 检查是否应该失败
                for i in valid_failure_indices:
                    if f"test{i}" in url:
                        raise Exception(f"模拟失败: {url}")
                
                # 成功的响应
                mock_response = Mock()
                mock_response.status = 200
                mock_response.text = AsyncMock(return_value=self._generate_valid_html())
                return mock_response
            
            engine.http_client.get = mock_get
            
            # 执行批量爬取
            results = await engine.scrape_batch(urls)
            
            # 验证结果
            expected_success = url_count - len(set(valid_failure_indices))
            assert len(results) == expected_success, \
                f"应该成功处理 {expected_success} 个URL，实际 {len(results)} 个"
            
            # 验证统计信息
            stats = engine.get_stats()
            assert stats['total_videos'] == url_count, "应该记录所有尝试的视频"
            assert stats['successful_videos'] == expected_success, "应该记录成功的视频数"
            assert stats['failed_videos'] == len(set(valid_failure_indices)), "应该记录失败的视频数"
        
        run_async(_test())
    
    @given(
        url_count=st.integers(min_value=2, max_value=5)
    )
    @settings(max_examples=15, deadline=10000)
    def test_batch_report_generation(self, url_count):
        """
        测试批量任务报告生成
        Feature: tencent-video-scraper, Property 8: 批量任务报告生成
        """
        async def _test():
            config = ScraperConfig()
            engine = ScraperEngine(config)
            
            # 生成测试URL列表
            urls = [f"https://v.qq.com/x/cover/test{i}.html" for i in range(url_count)]
            
            # 模拟成功的响应
            mock_response = Mock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=self._generate_valid_html())
            engine.http_client.get = AsyncMock(return_value=mock_response)
            
            # 记录进度回调
            progress_updates = []
            engine.set_progress_callback(lambda update: progress_updates.append(update))
            
            # 执行批量爬取
            results = await engine.scrape_batch(urls)
            
            # 验证报告生成
            assert len(progress_updates) > 0, "应该有进度更新"
            
            # 查找批量完成的回调
            batch_completed = [u for u in progress_updates if u.get('type') == 'batch_completed']
            assert len(batch_completed) > 0, "应该有批量完成的回调"
            
            report_callback = batch_completed[0]
            assert 'total_urls' in report_callback, "报告应该包含总URL数"
            assert 'successful_count' in report_callback, "报告应该包含成功数"
            assert 'failed_count' in report_callback, "报告应该包含失败数"
            
            # 验证报告数据正确性
            assert report_callback['total_urls'] == url_count, "总URL数应该正确"
            assert report_callback['successful_count'] == len(results), "成功数应该正确"
        
        run_async(_test())
    
    def test_empty_url_list_handling(self):
        """
        测试空URL列表的处理
        Feature: tencent-video-scraper, Property 6: 批量处理鲁棒性
        """
        async def _test():
            config = ScraperConfig()
            engine = ScraperEngine(config)
            
            # 执行空列表批量爬取
            results = await engine.scrape_batch([])
            
            # 应该返回空列表，不崩溃
            assert results == [], "空URL列表应该返回空结果"
            
            # 统计信息应该为0
            stats = engine.get_stats()
            assert stats['total_videos'] == 0, "空列表不应该有视频统计"
        
        run_async(_test())
    
    def _generate_valid_html(self) -> str:
        """生成有效的测试HTML"""
        return '''
        <html>
        <head>
            <title>测试视频 - 腾讯视频</title>
            <meta name="description" content="测试视频描述">
        </head>
        <body>
            <h1 class="video_title">测试视频标题</h1>
            <div class="video-duration">10:30</div>
            <div class="video-view-count">12345</div>
            <div class="video-publish-time">2024-01-01</div>
            <script>
                var videoUrl = "https://example.com/video.m3u8";
            </script>
        </body>
        </html>
        '''


class TestAdvancedScraperEngine:
    """测试高级爬虫引擎"""
    
    @given(
        retry_count=st.integers(min_value=1, max_value=3),
        success_on_attempt=st.integers(min_value=1, max_value=4)
    )
    @settings(max_examples=20, deadline=10000)
    def test_retry_mechanism(self, retry_count, success_on_attempt):
        """
        测试重试机制
        Feature: tencent-video-scraper, Property 4: 错误处理一致性
        """
        async def _test():
            config = ScraperConfig(max_retries=retry_count)
            engine = AdvancedScraperEngine(config)
            
            # 跟踪尝试次数
            attempt_count = [0]
            
            async def mock_get(url, **kwargs):
                attempt_count[0] += 1
                
                if attempt_count[0] < success_on_attempt:
                    raise Exception(f"模拟失败，尝试 {attempt_count[0]}")
                
                # 成功的响应
                mock_response = Mock()
                mock_response.status = 200
                mock_response.text = AsyncMock(return_value='''
                    <html>
                    <head><title>测试视频</title></head>
                    <body>
                        <h1 class="video_title">测试视频</h1>
                        <div class="video-duration">05:00</div>
                        <div class="video-view-count">1000</div>
                    </body>
                    </html>
                ''')
                return mock_response
            
            engine.http_client.get = mock_get
            
            test_url = "https://v.qq.com/x/cover/test.html"
            
            if success_on_attempt <= retry_count + 1:
                # 应该在重试范围内成功
                result = await engine.scrape_video_with_retry(test_url)
                assert result is not None, "应该成功获取视频数据"
                assert attempt_count[0] == success_on_attempt, f"应该在第 {success_on_attempt} 次尝试成功"
            else:
                # 应该在所有重试后失败
                with pytest.raises(Exception):
                    await engine.scrape_video_with_retry(test_url)
                assert attempt_count[0] == retry_count + 1, "应该尝试所有重试次数"
        
        run_async(_test())
    
    def test_concurrent_batch_processing(self):
        """
        测试并发批量处理
        Feature: tencent-video-scraper, Property 6: 批量处理鲁棒性
        """
        async def _test():
            config = ScraperConfig()
            engine = AdvancedScraperEngine(config)
            engine.max_concurrent = 3
            
            # 生成测试URL
            urls = [f"https://v.qq.com/x/cover/test{i}.html" for i in range(5)]
            
            # 模拟成功的响应
            mock_response = Mock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='''
                <html>
                <head><title>测试视频</title></head>
                <body>
                    <h1 class="video_title">测试视频</h1>
                    <div class="video-duration">05:00</div>
                    <div class="video-view-count">1000</div>
                </body>
                </html>
            ''')
            engine.http_client.get = AsyncMock(return_value=mock_response)
            
            # 执行并发批量爬取
            results = await engine.scrape_batch_concurrent(urls)
            
            # 验证结果
            assert len(results) == 5, "应该成功处理所有URL"
            
            # 验证统计信息
            stats = engine.get_stats()
            assert stats['successful_videos'] == 5, "应该记录所有成功的视频"
        
        run_async(_test())


class TestScraperEngineConfiguration:
    """测试爬虫引擎配置"""
    
    @given(
        rate_limit=st.floats(min_value=0.1, max_value=5.0),
        timeout=st.integers(min_value=10, max_value=60),
        max_retries=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=20, deadline=5000)
    def test_configuration_application(self, rate_limit, timeout, max_retries):
        """
        测试配置正确应用
        Feature: tencent-video-scraper, Property 4: 错误处理一致性
        """
        config = ScraperConfig(
            rate_limit=rate_limit,
            timeout=timeout,
            max_retries=max_retries
        )
        
        engine = ScraperEngine(config)
        
        # 验证配置应用
        assert engine.config.rate_limit == rate_limit, "速率限制应该正确应用"
        assert engine.config.timeout == timeout, "超时应该正确应用"
        assert engine.config.max_retries == max_retries, "重试次数应该正确应用"
        
        # 验证速率限制器配置
        assert engine.rate_limiter.rate == rate_limit, "速率限制器应该使用配置的速率"
    
    def test_progress_callback_setting(self):
        """
        测试进度回调设置
        Feature: tencent-video-scraper, Property 6: 批量处理鲁棒性
        """
        config = ScraperConfig()
        engine = ScraperEngine(config)
        
        # 设置回调
        callback_called = [False]
        
        def test_callback(update):
            callback_called[0] = True
        
        engine.set_progress_callback(test_callback)
        
        # 验证回调已设置
        assert engine.progress_callback is not None, "回调应该被设置"
        assert engine.progress_callback == test_callback, "回调应该是设置的函数"