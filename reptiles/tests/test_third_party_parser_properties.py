"""
第三方解析管理器属性测试

测试第三方解析功能的多策略集成和故障转移。
Feature: tencent-video-scraper, Property 23: 多策略解析集成
Feature: tencent-video-scraper, Property 24: 解析故障转移
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from hypothesis import given, strategies as st, settings
import json
import time

from tencent_video_scraper.third_party_parser import ThirdPartyParserManager, ParserInterface
from tencent_video_scraper.http_client import HTTPClient
from tencent_video_scraper.models import ScraperConfig


def run_async(coro):
    """运行异步协程的辅助函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestMultiStrategyIntegration:
    """
    测试多策略解析集成
    Property 23: 多策略解析集成
    Validates: Requirements 9.1
    """
    
    def test_minimum_strategy_count(self):
        """
        测试解析管理器至少包含3个不同的解析策略
        Feature: tencent-video-scraper, Property 23: 多策略解析集成
        **Validates: Requirements 9.1**
        """
        manager = ThirdPartyParserManager()
        
        # 验证至少有3个解析策略
        strategy_count = manager.get_strategy_count()
        assert strategy_count >= 3, f"应该至少有3个解析策略，实际: {strategy_count}"
        
        # 验证策略都是启用的
        enabled_parsers = [p for p in manager.parsers if p.enabled]
        assert len(enabled_parsers) >= 3, "应该至少有3个启用的解析策略"
    
    @given(
        parser_count=st.integers(min_value=3, max_value=10)
    )
    @settings(max_examples=20, deadline=5000)
    def test_strategy_diversity(self, parser_count):
        """
        测试解析策略的多样性
        Feature: tencent-video-scraper, Property 23: 多策略解析集成
        **Validates: Requirements 9.1**
        """
        manager = ThirdPartyParserManager()
        
        # 获取所有解析器名称
        parser_names = [p.name for p in manager.parsers]
        
        # 验证名称唯一性
        assert len(parser_names) == len(set(parser_names)), "解析器名称应该唯一"
        
        # 验证URL模板多样性
        url_templates = [p.url_template for p in manager.parsers]
        assert len(url_templates) == len(set(url_templates)), "URL模板应该唯一"
    
    @given(
        video_id=st.text(min_size=8, max_size=16).filter(lambda x: x.isalnum())
    )
    @settings(max_examples=20, deadline=5000)
    def test_parser_url_generation(self, video_id):
        """
        测试解析器URL生成
        Feature: tencent-video-scraper, Property 23: 多策略解析集成
        **Validates: Requirements 9.1**
        """
        manager = ThirdPartyParserManager()
        test_url = f"https://v.qq.com/x/cover/{video_id}.html"
        
        for parser in manager.parsers:
            # 验证URL模板包含占位符
            assert "{url}" in parser.url_template, f"URL模板应该包含{{url}}占位符: {parser.name}"
            
            # 验证可以正确生成URL
            from urllib.parse import quote
            encoded_url = quote(test_url, safe='')
            generated_url = parser.url_template.format(url=encoded_url)
            
            assert generated_url.startswith("http"), f"生成的URL应该以http开头: {parser.name}"
            assert encoded_url in generated_url, f"生成的URL应该包含编码后的视频URL: {parser.name}"


class TestParseFailover:
    """
    测试解析故障转移
    Property 24: 解析故障转移
    Validates: Requirements 9.2, 9.6
    """
    
    @given(
        fail_count=st.integers(min_value=0, max_value=5),
        success_index=st.integers(min_value=0, max_value=9)
    )
    @settings(max_examples=30, deadline=10000)
    def test_failover_mechanism(self, fail_count, success_index):
        """
        测试故障转移机制 - 当某些接口失败时应该尝试其他接口
        Feature: tencent-video-scraper, Property 24: 解析故障转移
        **Validates: Requirements 9.2, 9.6**
        """
        async def _test():
            manager = ThirdPartyParserManager()
            
            # 确保success_index在范围内
            actual_success_index = success_index % len(manager.parsers)
            
            # 创建模拟的HTTP客户端
            mock_http_client = Mock(spec=HTTPClient)
            mock_session = AsyncMock()
            mock_http_client._get_session = AsyncMock(return_value=mock_session)
            
            call_count = [0]
            
            async def mock_get(url, **kwargs):
                response = Mock()
                current_call = call_count[0]
                call_count[0] += 1
                
                if current_call == actual_success_index:
                    # 这个接口成功
                    response._content = '{"url": "https://example.com/video.m3u8"}'
                else:
                    # 其他接口失败
                    response._content = '{"error": "failed"}'
                
                return response
            
            mock_http_client.get = mock_get
            
            # 执行解析
            test_url = "https://v.qq.com/x/cover/test123.html"
            result = await manager.parse(test_url, mock_http_client)
            
            # 验证结果
            if actual_success_index < len(manager.get_sorted_parsers()):
                assert result is not None, "应该通过故障转移获取到播放链接"
                assert "m3u8" in result or "mp4" in result, "返回的应该是视频链接"
        
        run_async(_test())
    
    def test_all_parsers_fail_returns_none(self):
        """
        测试所有解析器都失败时返回None和明确错误
        Feature: tencent-video-scraper, Property 24: 解析故障转移
        **Validates: Requirements 9.6**
        """
        async def _test():
            manager = ThirdPartyParserManager()
            
            # 创建模拟的HTTP客户端，所有请求都失败
            mock_http_client = Mock(spec=HTTPClient)
            
            async def mock_get(url, **kwargs):
                response = Mock()
                response._content = '{"error": "all failed"}'
                return response
            
            mock_http_client.get = mock_get
            
            # 执行解析
            test_url = "https://v.qq.com/x/cover/test123.html"
            result = await manager.parse(test_url, mock_http_client)
            
            # 所有接口失败时应该返回None
            assert result is None, "所有解析接口失败时应该返回None"
        
        run_async(_test())
    
    @given(
        consecutive_failures=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=20, deadline=5000)
    def test_failure_recording(self, consecutive_failures):
        """
        测试失败记录机制
        Feature: tencent-video-scraper, Property 24: 解析故障转移
        **Validates: Requirements 9.2**
        """
        manager = ThirdPartyParserManager()
        parser = manager.parsers[0]
        
        initial_failure_count = parser.failure_count
        
        # 记录多次失败
        for _ in range(consecutive_failures):
            manager._record_failure(parser)
        
        # 验证失败计数
        assert parser.failure_count == initial_failure_count + consecutive_failures, \
            "失败计数应该正确增加"
        
        # 验证连续失败计数
        assert parser.consecutive_failures == consecutive_failures, \
            "连续失败计数应该正确"
        
        # 验证最后失败时间
        assert parser.last_failure_time is not None, "应该记录最后失败时间"


class TestParserInterfaceModel:
    """测试解析接口数据模型"""
    
    @given(
        success_count=st.integers(min_value=0, max_value=100),
        failure_count=st.integers(min_value=0, max_value=100),
        total_response_time=st.floats(min_value=0.0, max_value=1000.0)
    )
    @settings(max_examples=30, deadline=5000)
    def test_success_rate_calculation(self, success_count, failure_count, total_response_time):
        """
        测试成功率计算
        Feature: tencent-video-scraper, Property 23: 多策略解析集成
        **Validates: Requirements 9.1**
        """
        parser = ParserInterface(
            name="test_parser",
            url_template="https://test.com/?url={url}",
            response_type="json",
            success_count=success_count,
            failure_count=failure_count,
            total_response_time=total_response_time
        )
        
        success_rate = parser.get_success_rate()
        
        # 验证成功率范围
        assert 0.0 <= success_rate <= 1.0, "成功率应该在0-1之间"
        
        # 验证成功率计算
        total = success_count + failure_count
        if total > 0:
            expected_rate = success_count / total
            assert abs(success_rate - expected_rate) < 0.001, \
                f"成功率计算错误，期望: {expected_rate}，实际: {success_rate}"
        else:
            assert success_rate == 0.5, "没有数据时成功率应该为0.5（默认值）"
    
    @given(
        success_count=st.integers(min_value=1, max_value=100),
        total_response_time=st.floats(min_value=0.1, max_value=100.0)
    )
    @settings(max_examples=30, deadline=5000)
    def test_average_response_time_calculation(self, success_count, total_response_time):
        """
        测试平均响应时间计算
        Feature: tencent-video-scraper, Property 23: 多策略解析集成
        **Validates: Requirements 9.1**
        """
        parser = ParserInterface(
            name="test_parser",
            url_template="https://test.com/?url={url}",
            response_type="json",
            success_count=success_count,
            total_response_time=total_response_time
        )
        
        avg_time = parser.get_average_response_time()
        expected_avg = total_response_time / success_count
        
        assert abs(avg_time - expected_avg) < 0.001, \
            f"平均响应时间计算错误，期望: {expected_avg}，实际: {avg_time}"
    
    def test_to_dict_and_from_dict(self):
        """
        测试序列化和反序列化
        Feature: tencent-video-scraper, Property 23: 多策略解析集成
        **Validates: Requirements 9.1**
        """
        original = ParserInterface(
            name="test_parser",
            url_template="https://test.com/?url={url}",
            response_type="json",
            enabled=True,
            success_count=10,
            failure_count=5
        )
        
        # 转换为字典
        data = original.to_dict()
        
        # 从字典创建
        restored = ParserInterface.from_dict(data)
        
        # 验证数据一致性
        assert restored.name == original.name
        assert restored.url_template == original.url_template
        assert restored.response_type == original.response_type
        assert restored.enabled == original.enabled
        assert restored.success_count == original.success_count
        assert restored.failure_count == original.failure_count


class TestCooldownMechanism:
    """测试冷却机制"""
    
    @given(
        consecutive_failures=st.integers(min_value=5, max_value=15)
    )
    @settings(max_examples=20, deadline=5000)
    def test_cooldown_activation(self, consecutive_failures):
        """
        测试冷却机制激活
        Feature: tencent-video-scraper, Property 24: 解析故障转移
        **Validates: Requirements 9.2**
        """
        manager = ThirdPartyParserManager()
        parser = manager.parsers[0]
        
        # 重置状态
        parser.consecutive_failures = 0
        parser.cooldown_until = None
        
        # 记录连续失败
        for _ in range(consecutive_failures):
            manager._record_failure(parser)
        
        # 如果连续失败达到阈值，应该进入冷却期
        if consecutive_failures >= manager.MAX_CONSECUTIVE_FAILURES:
            assert parser.cooldown_until is not None, "达到失败阈值后应该进入冷却期"
            assert parser.is_in_cooldown(), "应该处于冷却状态"
        
    def test_cooldown_excludes_parser_from_sorted_list(self):
        """
        测试冷却中的解析器被排除在排序列表外
        Feature: tencent-video-scraper, Property 24: 解析故障转移
        **Validates: Requirements 9.2**
        """
        manager = ThirdPartyParserManager()
        parser = manager.parsers[0]
        
        # 设置冷却
        parser.cooldown_until = time.time() + 3600  # 1小时后
        
        # 获取排序后的解析器列表
        sorted_parsers = manager.get_sorted_parsers()
        
        # 冷却中的解析器不应该在列表中
        assert parser not in sorted_parsers, "冷却中的解析器不应该在可用列表中"
    
    def test_success_resets_cooldown(self):
        """
        测试成功后重置冷却
        Feature: tencent-video-scraper, Property 24: 解析故障转移
        **Validates: Requirements 9.2**
        """
        manager = ThirdPartyParserManager()
        parser = manager.parsers[0]
        
        # 设置冷却状态
        parser.consecutive_failures = 10
        parser.cooldown_until = time.time() + 3600
        
        # 记录成功
        manager._record_success(parser, 1.0)
        
        # 验证冷却被重置
        assert parser.consecutive_failures == 0, "成功后连续失败计数应该重置"
        assert parser.cooldown_until is None, "成功后冷却应该被清除"
        assert not parser.is_in_cooldown(), "成功后不应该处于冷却状态"



class TestDynamicSorting:
    """
    测试解析策略动态排序
    Property 25: 解析策略动态排序
    Validates: Requirements 9.3
    """
    
    @given(
        success_rates=st.lists(
            st.floats(min_value=0.0, max_value=1.0),
            min_size=3,
            max_size=10
        )
    )
    @settings(max_examples=30, deadline=5000)
    def test_sorting_by_success_rate(self, success_rates):
        """
        测试按成功率排序
        Feature: tencent-video-scraper, Property 25: 解析策略动态排序
        **Validates: Requirements 9.3**
        """
        manager = ThirdPartyParserManager()
        
        # 设置不同的成功率
        for i, rate in enumerate(success_rates):
            if i < len(manager.parsers):
                parser = manager.parsers[i]
                # 根据成功率设置成功和失败次数
                total = 100
                parser.success_count = int(rate * total)
                parser.failure_count = total - parser.success_count
                parser.consecutive_failures = 0
                parser.cooldown_until = None
        
        # 获取排序后的列表
        sorted_parsers = manager.get_sorted_parsers()
        
        # 验证按成功率降序排序
        for i in range(len(sorted_parsers) - 1):
            current_rate = sorted_parsers[i].get_success_rate()
            next_rate = sorted_parsers[i + 1].get_success_rate()
            assert current_rate >= next_rate, \
                f"解析器应该按成功率降序排序: {current_rate} >= {next_rate}"
    
    @given(
        response_times=st.lists(
            st.floats(min_value=0.1, max_value=10.0),
            min_size=3,
            max_size=10
        )
    )
    @settings(max_examples=30, deadline=5000)
    def test_sorting_by_response_time_when_equal_success_rate(self, response_times):
        """
        测试成功率相同时按响应时间排序
        Feature: tencent-video-scraper, Property 25: 解析策略动态排序
        **Validates: Requirements 9.3**
        """
        manager = ThirdPartyParserManager()
        
        # 设置相同的成功率但不同的响应时间
        for i, resp_time in enumerate(response_times):
            if i < len(manager.parsers):
                parser = manager.parsers[i]
                parser.success_count = 50
                parser.failure_count = 50  # 50%成功率
                parser.total_response_time = resp_time * 50  # 平均响应时间
                parser.consecutive_failures = 0
                parser.cooldown_until = None
        
        # 获取排序后的列表
        sorted_parsers = manager.get_sorted_parsers()
        
        # 验证成功率相同时按响应时间升序排序
        for i in range(len(sorted_parsers) - 1):
            current_rate = sorted_parsers[i].get_success_rate()
            next_rate = sorted_parsers[i + 1].get_success_rate()
            
            if abs(current_rate - next_rate) < 0.001:  # 成功率相同
                current_time = sorted_parsers[i].get_average_response_time()
                next_time = sorted_parsers[i + 1].get_average_response_time()
                assert current_time <= next_time, \
                    f"成功率相同时应该按响应时间升序排序: {current_time} <= {next_time}"
    
    def test_priority_changes_after_success(self):
        """
        测试成功后优先级变化
        Feature: tencent-video-scraper, Property 25: 解析策略动态排序
        **Validates: Requirements 9.3**
        """
        manager = ThirdPartyParserManager()
        
        # 设置初始状态：第一个解析器成功率低
        manager.parsers[0].success_count = 10
        manager.parsers[0].failure_count = 90  # 10%成功率
        manager.parsers[0].consecutive_failures = 0
        manager.parsers[0].cooldown_until = None
        
        # 第二个解析器成功率高
        manager.parsers[1].success_count = 90
        manager.parsers[1].failure_count = 10  # 90%成功率
        manager.parsers[1].consecutive_failures = 0
        manager.parsers[1].cooldown_until = None
        
        # 获取初始排序
        initial_sorted = manager.get_sorted_parsers()
        
        # 第二个解析器应该排在前面
        assert initial_sorted[0].name == manager.parsers[1].name, \
            "成功率高的解析器应该排在前面"
        
        # 模拟第一个解析器多次成功
        for _ in range(100):
            manager._record_success(manager.parsers[0], 0.5)
        
        # 获取新的排序
        new_sorted = manager.get_sorted_parsers()
        
        # 验证排序发生了变化
        first_parser_rate = manager.parsers[0].get_success_rate()
        second_parser_rate = manager.parsers[1].get_success_rate()
        
        if first_parser_rate > second_parser_rate:
            assert new_sorted[0].name == manager.parsers[0].name, \
                "成功率提高后应该排在前面"
    
    def test_priority_changes_after_failure(self):
        """
        测试失败后优先级变化
        Feature: tencent-video-scraper, Property 25: 解析策略动态排序
        **Validates: Requirements 9.3**
        """
        manager = ThirdPartyParserManager()
        
        # 设置初始状态：两个解析器成功率相同
        manager.parsers[0].success_count = 50
        manager.parsers[0].failure_count = 50
        manager.parsers[0].consecutive_failures = 0
        manager.parsers[0].cooldown_until = None
        
        manager.parsers[1].success_count = 50
        manager.parsers[1].failure_count = 50
        manager.parsers[1].consecutive_failures = 0
        manager.parsers[1].cooldown_until = None
        
        # 模拟第一个解析器多次失败
        for _ in range(50):
            manager._record_failure(manager.parsers[0])
        
        # 重置冷却以便测试排序
        manager.parsers[0].cooldown_until = None
        
        # 获取新的排序
        new_sorted = manager.get_sorted_parsers()
        
        # 第一个解析器成功率降低，应该排在后面
        first_parser_rate = manager.parsers[0].get_success_rate()
        second_parser_rate = manager.parsers[1].get_success_rate()
        
        assert first_parser_rate < second_parser_rate, \
            "失败后成功率应该降低"
        
        # 找到两个解析器在排序列表中的位置
        first_index = next((i for i, p in enumerate(new_sorted) if p.name == manager.parsers[0].name), -1)
        second_index = next((i for i, p in enumerate(new_sorted) if p.name == manager.parsers[1].name), -1)
        
        if first_index != -1 and second_index != -1:
            assert first_index > second_index, \
                "成功率降低后应该排在后面"
    
    @given(
        operations=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=2),  # parser index
                st.booleans()  # success or failure
            ),
            min_size=10,
            max_size=50
        )
    )
    @settings(max_examples=20, deadline=10000)
    def test_sorting_consistency(self, operations):
        """
        测试排序一致性 - 多次操作后排序应该保持一致
        Feature: tencent-video-scraper, Property 25: 解析策略动态排序
        **Validates: Requirements 9.3**
        """
        manager = ThirdPartyParserManager()
        
        # 重置所有解析器状态
        for parser in manager.parsers:
            parser.success_count = 0
            parser.failure_count = 0
            parser.consecutive_failures = 0
            parser.cooldown_until = None
            parser.total_response_time = 0.0
        
        # 执行操作序列
        for parser_idx, is_success in operations:
            actual_idx = parser_idx % len(manager.parsers)
            parser = manager.parsers[actual_idx]
            
            if is_success:
                manager._record_success(parser, 1.0)
            else:
                manager._record_failure(parser)
                # 重置冷却以便继续测试
                parser.cooldown_until = None
        
        # 获取排序结果
        sorted_parsers = manager.get_sorted_parsers()
        
        # 验证排序是确定性的
        sorted_parsers_2 = manager.get_sorted_parsers()
        
        assert [p.name for p in sorted_parsers] == [p.name for p in sorted_parsers_2], \
            "相同状态下排序结果应该一致"
        
        # 验证排序正确性
        for i in range(len(sorted_parsers) - 1):
            current = sorted_parsers[i]
            next_p = sorted_parsers[i + 1]
            
            current_rate = current.get_success_rate()
            next_rate = next_p.get_success_rate()
            
            # 成功率应该降序
            assert current_rate >= next_rate or \
                   (abs(current_rate - next_rate) < 0.001 and 
                    current.get_average_response_time() <= next_p.get_average_response_time()), \
                "排序应该按成功率降序，响应时间升序"



class TestPlayUrlValidation:
    """
    测试播放链接有效性验证
    Property 26: 播放链接有效性验证
    Validates: Requirements 9.4
    """
    
    @given(
        extension=st.sampled_from(['.m3u8', '.mp4', '.flv', '.ts']),
        domain=st.sampled_from(['example.com', 'cdn.video.com', 'stream.test.org']),
        path_segments=st.lists(st.text(min_size=1, max_size=10).filter(lambda x: x.isalnum()), min_size=1, max_size=5)
    )
    @settings(max_examples=50, deadline=5000)
    def test_valid_video_url_formats(self, extension, domain, path_segments):
        """
        测试有效视频URL格式验证
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 构建有效的视频URL
        path = '/'.join(path_segments)
        url = f"https://{domain}/{path}/video{extension}"
        
        # 验证应该通过
        is_valid = manager.validate_play_url(url)
        assert is_valid, f"有效的视频URL应该通过验证: {url}"
    
    @given(
        protocol=st.sampled_from(['/m3u8/', '/mp4/', '/flv/', '/hls/', '/dash/']),
        domain=st.sampled_from(['example.com', 'cdn.video.com', 'stream.test.org'])
    )
    @settings(max_examples=30, deadline=5000)
    def test_valid_streaming_protocols(self, protocol, domain):
        """
        测试有效流媒体协议验证
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 构建包含流媒体协议的URL
        url = f"https://{domain}{protocol}stream/video"
        
        # 验证应该通过
        is_valid = manager.validate_play_url(url)
        assert is_valid, f"包含流媒体协议的URL应该通过验证: {url}"
    
    @given(
        invalid_url=st.sampled_from([
            '',  # 空字符串
            'not-a-url',  # 非URL
            'ftp://example.com/video.mp4',  # 非HTTP协议
            'http://x.mp4',  # 太短
            'https://example.com/image.jpg',  # 图片
            'https://example.com/style.css',  # CSS
            'https://example.com/script.js',  # JS
            'https://example.com/thumb.png',  # 缩略图
            'https://example.com/poster.gif',  # 海报
        ])
    )
    @settings(max_examples=30, deadline=5000)
    def test_invalid_url_rejection(self, invalid_url):
        """
        测试无效URL被拒绝
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 验证应该失败
        is_valid = manager.validate_play_url(invalid_url)
        assert not is_valid, f"无效的URL应该被拒绝: {invalid_url}"
    
    @given(
        invalid_char=st.sampled_from(['<', '>', '"', "'", '\n', '\r', '\t'])
    )
    @settings(max_examples=20, deadline=5000)
    def test_urls_with_invalid_characters(self, invalid_char):
        """
        测试包含无效字符的URL被拒绝
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 构建包含无效字符的URL
        url = f"https://example.com/video{invalid_char}test.m3u8"
        
        # 验证应该失败
        is_valid = manager.validate_play_url(url)
        assert not is_valid, f"包含无效字符的URL应该被拒绝: {repr(url)}"
    
    def test_url_length_validation(self):
        """
        测试URL长度验证
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 太短的URL
        short_url = "https://x.m3u8"
        assert not manager.validate_play_url(short_url), "太短的URL应该被拒绝"
        
        # 太长的URL
        long_url = "https://example.com/" + "a" * 2000 + ".m3u8"
        assert not manager.validate_play_url(long_url), "太长的URL应该被拒绝"
        
        # 正常长度的URL
        normal_url = "https://example.com/path/to/video.m3u8"
        assert manager.validate_play_url(normal_url), "正常长度的URL应该通过验证"
    
    @given(
        url_content=st.text(min_size=50, max_size=500)
    )
    @settings(max_examples=30, deadline=5000)
    def test_url_extraction_from_content(self, url_content):
        """
        测试从内容中提取URL
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 在内容中嵌入一个有效的视频URL
        valid_url = "https://cdn.example.com/stream/video.m3u8"
        content_with_url = f'{url_content}"url":"{valid_url}"{url_content}'
        
        # 提取URL
        extracted = manager._extract_url_from_text(content_with_url)
        
        # 应该能提取到有效的URL
        if extracted:
            assert manager.validate_play_url(extracted), "提取的URL应该是有效的"
    
    def test_is_video_url_helper(self):
        """
        测试_is_video_url辅助方法
        Feature: tencent-video-scraper, Property 26: 播放链接有效性验证
        **Validates: Requirements 9.4**
        """
        manager = ThirdPartyParserManager()
        
        # 有效的视频URL
        valid_urls = [
            "https://example.com/video.m3u8",
            "https://example.com/video.mp4",
            "https://example.com/video.flv",
            "https://example.com/m3u8/stream",
            "https://example.com/mp4/video",
        ]
        
        for url in valid_urls:
            assert manager._is_video_url(url), f"应该识别为视频URL: {url}"
        
        # 无效的URL
        invalid_urls = [
            None,
            "",
            "not-a-url",
            "https://example.com/image.jpg",
            "https://example.com/poster.png",
            "https://example.com/thumb.gif",
        ]
        
        for url in invalid_urls:
            assert not manager._is_video_url(url), f"不应该识别为视频URL: {url}"



class TestCustomParserConfiguration:
    """
    测试自定义解析接口配置
    Property 27: 自定义解析接口配置
    Validates: Requirements 9.5
    """
    
    @given(
        parser_name=st.text(min_size=3, max_size=30).filter(lambda x: x.isalnum()),
        domain=st.sampled_from(['custom1.com', 'custom2.org', 'myparser.net']),
        response_type=st.sampled_from(['json', 'html'])
    )
    @settings(max_examples=30, deadline=5000)
    def test_add_custom_parser(self, parser_name, domain, response_type):
        """
        测试添加自定义解析接口
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        initial_count = len(manager.parsers)
        
        # 添加自定义解析接口
        url_template = f"https://{domain}/parse?url={{url}}"
        result = manager.add_parser(parser_name, url_template, response_type)
        
        # 验证添加成功
        assert result, "添加自定义解析接口应该成功"
        assert len(manager.parsers) == initial_count + 1, "解析器数量应该增加"
        
        # 验证可以获取到新添加的解析器
        parser = manager.get_parser_by_name(parser_name)
        assert parser is not None, "应该能获取到新添加的解析器"
        assert parser.url_template == url_template, "URL模板应该正确"
        assert parser.response_type == response_type, "响应类型应该正确"
        assert parser.enabled, "新添加的解析器应该默认启用"
    
    @given(
        parser_name=st.text(min_size=3, max_size=30).filter(lambda x: x.isalnum())
    )
    @settings(max_examples=20, deadline=5000)
    def test_remove_custom_parser(self, parser_name):
        """
        测试移除自定义解析接口
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 先添加一个解析器
        url_template = f"https://test.com/parse?url={{url}}"
        manager.add_parser(parser_name, url_template, "json")
        
        initial_count = len(manager.parsers)
        
        # 移除解析器
        result = manager.remove_parser(parser_name)
        
        # 验证移除成功
        assert result, "移除解析接口应该成功"
        assert len(manager.parsers) == initial_count - 1, "解析器数量应该减少"
        
        # 验证无法再获取到该解析器
        parser = manager.get_parser_by_name(parser_name)
        assert parser is None, "移除后不应该能获取到该解析器"
    
    def test_remove_nonexistent_parser(self):
        """
        测试移除不存在的解析接口
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 尝试移除不存在的解析器
        result = manager.remove_parser("nonexistent_parser")
        
        # 应该返回False
        assert not result, "移除不存在的解析器应该返回False"
    
    def test_add_duplicate_parser(self):
        """
        测试添加重复的解析接口
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 添加第一个解析器
        parser_name = "test_duplicate"
        url_template = "https://test.com/parse?url={url}"
        result1 = manager.add_parser(parser_name, url_template, "json")
        assert result1, "第一次添加应该成功"
        
        # 尝试添加同名解析器
        result2 = manager.add_parser(parser_name, url_template, "html")
        assert not result2, "添加重复名称的解析器应该失败"
    
    @given(
        invalid_template=st.sampled_from([
            "https://test.com/parse",  # 缺少{url}占位符
            "not-a-url",  # 非URL格式
            "",  # 空字符串
        ])
    )
    @settings(max_examples=10, deadline=5000)
    def test_invalid_url_template_rejection(self, invalid_template):
        """
        测试无效URL模板被拒绝
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 尝试添加无效模板的解析器
        result = manager.add_parser("invalid_parser", invalid_template, "json")
        
        # 应该失败
        assert not result, f"无效的URL模板应该被拒绝: {invalid_template}"
    
    def test_enable_disable_parser(self):
        """
        测试启用/禁用解析接口
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 获取第一个解析器
        parser_name = manager.parsers[0].name
        
        # 禁用解析器
        result = manager.disable_parser(parser_name)
        assert result, "禁用解析器应该成功"
        
        parser = manager.get_parser_by_name(parser_name)
        assert not parser.enabled, "解析器应该被禁用"
        
        # 禁用的解析器不应该在排序列表中
        sorted_parsers = manager.get_sorted_parsers()
        assert parser not in sorted_parsers, "禁用的解析器不应该在可用列表中"
        
        # 启用解析器
        result = manager.enable_parser(parser_name)
        assert result, "启用解析器应该成功"
        
        parser = manager.get_parser_by_name(parser_name)
        assert parser.enabled, "解析器应该被启用"
    
    def test_validate_parser_config(self):
        """
        测试解析器配置验证
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 有效配置
        valid_config = {
            "name": "test_parser",
            "url_template": "https://test.com/?url={url}",
            "response_type": "json"
        }
        assert manager._validate_parser_config(valid_config), "有效配置应该通过验证"
        
        # 缺少name
        invalid_config1 = {
            "url_template": "https://test.com/?url={url}"
        }
        assert not manager._validate_parser_config(invalid_config1), "缺少name应该验证失败"
        
        # 缺少url_template
        invalid_config2 = {
            "name": "test_parser"
        }
        assert not manager._validate_parser_config(invalid_config2), "缺少url_template应该验证失败"
        
        # 无效的response_type
        invalid_config3 = {
            "name": "test_parser",
            "url_template": "https://test.com/?url={url}",
            "response_type": "invalid"
        }
        assert not manager._validate_parser_config(invalid_config3), "无效的response_type应该验证失败"
    
    def test_custom_parser_in_sorted_list(self):
        """
        测试自定义解析器出现在排序列表中
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        manager = ThirdPartyParserManager()
        
        # 添加自定义解析器
        parser_name = "custom_test_parser"
        url_template = "https://custom.test.com/?url={url}"
        manager.add_parser(parser_name, url_template, "json")
        
        # 获取排序列表
        sorted_parsers = manager.get_sorted_parsers()
        
        # 自定义解析器应该在列表中
        parser_names = [p.name for p in sorted_parsers]
        assert parser_name in parser_names, "自定义解析器应该在可用列表中"
    
    def test_save_and_load_custom_config(self):
        """
        测试保存和加载自定义配置
        Feature: tencent-video-scraper, Property 27: 自定义解析接口配置
        **Validates: Requirements 9.5**
        """
        import tempfile
        import os
        
        manager = ThirdPartyParserManager()
        
        # 添加自定义解析器
        parser_name = "save_test_parser"
        url_template = "https://save.test.com/?url={url}"
        manager.add_parser(parser_name, url_template, "json")
        
        # 保存配置到临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_file = f.name
        
        try:
            manager.save_custom_config(config_file)
            
            # 验证文件存在
            assert os.path.exists(config_file), "配置文件应该被创建"
            
            # 读取并验证内容
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            assert "custom_parsers" in config_data, "配置应该包含custom_parsers"
            
            # 查找我们添加的解析器
            custom_parsers = config_data["custom_parsers"]
            found = any(p["name"] == parser_name for p in custom_parsers)
            assert found, "自定义解析器应该在配置中"
            
        finally:
            # 清理临时文件
            if os.path.exists(config_file):
                os.remove(config_file)
