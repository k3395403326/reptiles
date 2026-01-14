"""
SVIP处理器属性测试

测试SVIP内容绕过功能。
Feature: tencent-video-scraper, Property 3: SVIP内容绕过
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from hypothesis import given, strategies as st, settings
import json

from tencent_video_scraper.svip_handler import (
    SVIPHandler, AdvancedSVIPHandler,
    HeaderBypassStrategy, CookieBypassStrategy, TokenBypassStrategy
)
from tencent_video_scraper.http_client import HTTPClient
from tencent_video_scraper.models import ScraperConfig


def run_async(coro):
    """运行异步协程的辅助函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSVIPContentBypass:
    """测试SVIP内容绕过"""
    
    @given(
        video_id=st.text(min_size=8, max_size=32).filter(lambda x: x.isalnum()),
        quality=st.sampled_from(['1080p', '720p', '480p']),
        bypass_success=st.booleans()
    )
    @settings(max_examples=30, deadline=5000)
    def test_svip_bypass_capability(self, video_id, quality, bypass_success):
        """
        测试SVIP绕过能力 - 对于SVIP内容应该能够绕过限制获取播放链接
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        async def _test():
            # 创建模拟的HTTP客户端
            mock_http_client = Mock(spec=HTTPClient)
            mock_response = Mock()
            
            if bypass_success:
                # 模拟成功的API响应
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={
                    'data': {
                        'videoUrl': f'https://example.com/video_{video_id}_{quality}.m3u8'
                    }
                })
            else:
                # 模拟失败的响应
                mock_response.status = 403
                mock_response.json = AsyncMock(return_value={'error': 'access_denied'})
            
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_http_client.headers = {'User-Agent': 'test'}
            
            # 创建SVIP处理器
            handler = SVIPHandler()
            
            # 生成包含SVIP标识的HTML
            html = self._generate_svip_html(video_id, quality)
            url = f"https://v.qq.com/x/cover/{video_id}.html"
            
            # 执行绕过尝试
            result = await handler.bypass_svip_restriction(url, html, mock_http_client)
            
            if bypass_success:
                # 应该成功获取播放链接
                assert result is not None, "SVIP绕过应该成功返回播放链接"
                assert isinstance(result, str), "返回的播放链接应该是字符串"
                assert result.startswith('http'), "播放链接应该是有效的HTTP URL"
                assert video_id in result or quality in result, "播放链接应该包含视频ID或画质信息"
                
                # 验证统计信息
                stats = handler.get_stats()
                assert stats['bypass_attempts'] > 0, "应该记录绕过尝试次数"
                assert stats['bypass_successes'] > 0, "应该记录绕过成功次数"
            else:
                # 绕过失败时应该返回None，但不应该崩溃
                assert result is None, "绕过失败时应该返回None"
                
                # 验证统计信息
                stats = handler.get_stats()
                assert stats['bypass_attempts'] > 0, "应该记录绕过尝试次数"
        
        run_async(_test())
    
    @given(
        svip_indicators=st.lists(
            st.sampled_from(['svip', 'vip', '会员', '专享', 'premium', '付费']),
            min_size=1, max_size=3
        ),
        video_id=st.text(min_size=8, max_size=16).filter(lambda x: x.isalnum())
    )
    @settings(max_examples=30, deadline=5000)
    def test_svip_content_detection(self, svip_indicators, video_id):
        """
        测试SVIP内容检测准确性
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = SVIPHandler()
        
        # 生成包含SVIP标识的HTML
        html_parts = [f"<html><body><h1>视频{video_id}</h1>"]
        
        for indicator in svip_indicators:
            if indicator in ['svip', 'vip', 'premium']:
                html_parts.append(f'<div class="{indicator}-mark">会员专享</div>')
            else:
                html_parts.append(f'<span>{indicator}内容</span>')
        
        html_parts.append("</body></html>")
        html = "".join(html_parts)
        
        # 检测SVIP内容
        is_svip = handler.is_svip_content(html)
        
        # 应该正确检测到SVIP内容
        assert is_svip, f"应该检测到SVIP内容，标识符: {svip_indicators}"
        
        # 验证统计信息
        stats = handler.get_stats()
        assert stats['svip_detections'] > 0, "应该记录SVIP检测次数"
    
    @given(
        strategy_count=st.integers(min_value=1, max_value=3),
        success_strategy_index=st.integers(min_value=0, max_value=2)
    )
    @settings(max_examples=20, deadline=5000)
    def test_strategy_fallback_mechanism(self, strategy_count, success_strategy_index):
        """
        测试策略回退机制 - 当某个策略失败时应该尝试其他策略
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        async def _test():
            # 确保成功策略索引在范围内
            success_strategy_index = success_strategy_index % strategy_count
            
            # 创建模拟的HTTP客户端
            mock_http_client = Mock(spec=HTTPClient)
            mock_http_client.headers = {'User-Agent': 'test'}
            
            # 创建SVIP处理器
            handler = SVIPHandler()
            
            # 只保留指定数量的策略
            handler.bypass_strategies = handler.bypass_strategies[:strategy_count]
            
            # 模拟策略行为
            for i, strategy in enumerate(handler.bypass_strategies):
                if i == success_strategy_index:
                    # 这个策略成功
                    strategy.bypass = AsyncMock(return_value="https://example.com/success.m3u8")
                else:
                    # 其他策略失败
                    strategy.bypass = AsyncMock(return_value=None)
            
            # 执行绕过
            html = '<html><body><div class="svip-mark">会员专享</div></body></html>'
            url = "https://v.qq.com/test"
            
            result = await handler.bypass_svip_restriction(url, html, mock_http_client)
            
            # 应该成功获取结果
            assert result is not None, "应该通过回退策略获取到播放链接"
            assert result == "https://example.com/success.m3u8", "应该返回成功策略的结果"
            
            # 验证所有策略都被尝试了（直到成功为止）
            for i, strategy in enumerate(handler.bypass_strategies):
                if i <= success_strategy_index:
                    strategy.bypass.assert_called_once()
                else:
                    # 成功后的策略不应该被调用
                    strategy.bypass.assert_not_called()
        
        run_async(_test())
    
    @given(
        html_structure=st.sampled_from(['json_data', 'html_elements', 'mixed']),
        video_id=st.text(min_size=8, max_size=16).filter(lambda x: x.isalnum())
    )
    @settings(max_examples=30, deadline=5000)
    def test_multiple_detection_methods(self, html_structure, video_id):
        """
        测试多种SVIP检测方法
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = SVIPHandler()
        
        # 根据结构类型生成不同的HTML
        if html_structure == 'json_data':
            html = f'''
            <html>
            <body>
                <script>
                    window.videoData = {{
                        "vid": "{video_id}",
                        "isSvip": true,
                        "isVip": true
                    }};
                </script>
            </body>
            </html>
            '''
        elif html_structure == 'html_elements':
            html = f'''
            <html>
            <body>
                <div class="video-info">
                    <h1>视频{video_id}</h1>
                    <div class="svip-mark">超级影视VIP</div>
                    <div data-vip="true">会员专享内容</div>
                </div>
            </body>
            </html>
            '''
        else:  # mixed
            html = f'''
            <html>
            <body>
                <div class="vip-content">腾讯视频VIP专享</div>
                <script>
                    var config = {{"isPaid": true, "vid": "{video_id}"}};
                </script>
            </body>
            </html>
            '''
        
        # 检测SVIP内容
        is_svip = handler.is_svip_content(html)
        
        # 应该正确检测到SVIP内容
        assert is_svip, f"应该检测到SVIP内容，结构类型: {html_structure}"
    
    def test_non_svip_content_detection(self):
        """
        测试非SVIP内容的正确识别
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = SVIPHandler()
        
        # 生成普通内容的HTML
        html = '''
        <html>
        <body>
            <div class="video-info">
                <h1>普通视频</h1>
                <div class="free-content">免费观看</div>
                <div class="public-video">公开视频</div>
            </div>
        </body>
        </html>
        '''
        
        # 检测SVIP内容
        is_svip = handler.is_svip_content(html)
        
        # 不应该检测为SVIP内容
        assert not is_svip, "普通内容不应该被检测为SVIP内容"
    
    def _generate_svip_html(self, video_id: str, quality: str) -> str:
        """生成包含SVIP标识的测试HTML"""
        return f'''
        <html>
        <head>
            <title>SVIP视频 - 腾讯视频</title>
        </head>
        <body>
            <div class="video-container">
                <h1>SVIP专享视频</h1>
                <div class="svip-mark">会员专享</div>
                <div class="video-info" data-vid="{video_id}">
                    <span class="quality">{quality}</span>
                </div>
            </div>
            <script>
                window.videoInfo = {{
                    "vid": "{video_id}",
                    "isSvip": true,
                    "quality": "{quality}"
                }};
            </script>
        </body>
        </html>
        '''


class TestSVIPBypassStrategies:
    """测试SVIP绕过策略"""
    
    @given(
        strategy_type=st.sampled_from(['header', 'cookie', 'token']),
        video_id=st.text(min_size=8, max_size=16).filter(lambda x: x.isalnum())
    )
    @settings(max_examples=30, deadline=5000)
    def test_individual_strategy_execution(self, strategy_type, video_id):
        """
        测试单个策略的执行
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        async def _test():
            # 创建对应的策略
            if strategy_type == 'header':
                strategy = HeaderBypassStrategy()
            elif strategy_type == 'cookie':
                strategy = CookieBypassStrategy()
            else:  # token
                strategy = TokenBypassStrategy()
            
            # 创建模拟的HTTP客户端
            mock_http_client = Mock(spec=HTTPClient)
            mock_http_client.headers = {'User-Agent': 'test'}
            mock_http_client.session = Mock()
            mock_http_client.session.cookie_jar = Mock()
            mock_http_client.session.cookie_jar.update_cookies = Mock()
            
            # 模拟成功的响应
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'data': {'url': f'https://example.com/{video_id}.m3u8'}
            })
            mock_response.text = AsyncMock(return_value=f'<html><script>var url="{video_id}.m3u8";</script></html>')
            
            mock_http_client.get = AsyncMock(return_value=mock_response)
            
            # 生成测试HTML
            html = f'<html><body><div data-vid="{video_id}">SVIP内容</div></body></html>'
            url = f"https://v.qq.com/x/cover/{video_id}.html"
            
            # 执行策略
            result = await strategy.bypass(url, html, mock_http_client)
            
            # 验证策略执行
            assert mock_http_client.get.called, f"{strategy_type}策略应该发送HTTP请求"
            
            # 验证统计信息更新
            initial_success = strategy.success_count
            initial_failure = strategy.failure_count
            
            if result:
                assert strategy.success_count > initial_success, "成功时应该更新成功计数"
            else:
                assert strategy.failure_count > initial_failure, "失败时应该更新失败计数"
        
        run_async(_test())
    
    @given(
        success_count=st.integers(min_value=0, max_value=10),
        failure_count=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=30, deadline=5000)
    def test_strategy_success_rate_calculation(self, success_count, failure_count):
        """
        测试策略成功率计算
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        strategy = HeaderBypassStrategy()
        
        # 设置统计数据
        strategy.success_count = success_count
        strategy.failure_count = failure_count
        
        # 计算成功率
        success_rate = strategy.get_success_rate()
        
        # 验证成功率计算
        total = success_count + failure_count
        if total > 0:
            expected_rate = success_count / total
            assert abs(success_rate - expected_rate) < 0.001, \
                f"成功率计算错误，期望: {expected_rate}，实际: {success_rate}"
        else:
            assert success_rate == 0.0, "没有尝试时成功率应该为0"
        
        # 验证成功率范围
        assert 0.0 <= success_rate <= 1.0, "成功率应该在0-1之间"


class TestAdvancedSVIPHandler:
    """测试高级SVIP处理器"""
    
    def test_advanced_handler_initialization(self):
        """
        测试高级处理器初始化
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = AdvancedSVIPHandler()
        
        # 验证包含更多策略
        assert len(handler.bypass_strategies) > 3, "高级处理器应该包含更多绕过策略"
        
        # 验证策略名称
        strategy_names = [s.name for s in handler.bypass_strategies]
        expected_advanced_strategies = [
            'user_agent_rotation',
            'proxy_rotation', 
            'timing_attack'
        ]
        
        for strategy_name in expected_advanced_strategies:
            assert strategy_name in strategy_names, f"应该包含{strategy_name}策略"
    
    @given(
        config_params=st.fixed_dictionaries({
            'rate_limit': st.floats(min_value=0.1, max_value=5.0),
            'timeout': st.integers(min_value=10, max_value=60),
            'max_retries': st.integers(min_value=1, max_value=5)
        })
    )
    @settings(max_examples=20, deadline=5000)
    def test_handler_configuration(self, config_params):
        """
        测试处理器配置
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        config = ScraperConfig(**config_params)
        handler = SVIPHandler(config)
        
        # 验证配置应用
        assert handler.config.rate_limit == config_params['rate_limit'], "速率限制配置应该正确应用"
        assert handler.config.timeout == config_params['timeout'], "超时配置应该正确应用"
        assert handler.config.max_retries == config_params['max_retries'], "重试配置应该正确应用"
        
        # 验证统计信息初始化
        stats = handler.get_stats()
        assert stats['bypass_attempts'] == 0, "初始绕过尝试次数应该为0"
        assert stats['bypass_successes'] == 0, "初始绕过成功次数应该为0"
        assert stats['overall_success_rate'] == 0.0, "初始总体成功率应该为0"


class TestSVIPHandlerEdgeCases:
    """测试SVIP处理器边界情况"""
    
    def test_empty_html_handling(self):
        """
        测试空HTML的处理
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = SVIPHandler()
        
        # 测试空HTML
        is_svip = handler.is_svip_content("")
        assert not is_svip, "空HTML不应该被检测为SVIP内容"
        
        # 测试只有空白的HTML
        is_svip = handler.is_svip_content("   \n\t  ")
        assert not is_svip, "只包含空白的HTML不应该被检测为SVIP内容"
    
    def test_malformed_html_handling(self):
        """
        测试格式错误HTML的处理
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = SVIPHandler()
        
        # 测试格式错误的HTML
        malformed_html = '<html><body><div class="svip">会员</div><unclosed_tag></body>'
        
        # 不应该崩溃
        try:
            is_svip = handler.is_svip_content(malformed_html)
            assert isinstance(is_svip, bool), "应该返回布尔值"
        except Exception as e:
            pytest.fail(f"处理格式错误的HTML时不应该抛出异常: {e}")
    
    @given(
        large_html_size=st.integers(min_value=1000, max_value=10000)
    )
    @settings(max_examples=10, deadline=5000)
    def test_large_html_performance(self, large_html_size):
        """
        测试大HTML文件的处理性能
        Feature: tencent-video-scraper, Property 3: SVIP内容绕过
        """
        handler = SVIPHandler()
        
        # 生成大HTML文件
        html_parts = ["<html><body>"]
        for i in range(large_html_size // 100):
            html_parts.append(f"<div>内容{i}</div>")
        html_parts.append('<div class="svip-mark">会员专享</div>')
        html_parts.append("</body></html>")
        
        large_html = "".join(html_parts)
        
        # 测试处理时间
        import time
        start_time = time.time()
        is_svip = handler.is_svip_content(large_html)
        end_time = time.time()
        
        # 应该在合理时间内完成
        processing_time = end_time - start_time
        assert processing_time < 1.0, f"处理大HTML文件耗时过长: {processing_time:.2f}秒"
        
        # 应该正确检测
        assert is_svip, "应该正确检测到SVIP内容"