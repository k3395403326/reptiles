"""
速率限制器属性测试

测试速率限制器的速率限制遵守和指数退避算法。
Feature: tencent-video-scraper, Property 7: 速率限制遵守
Feature: tencent-video-scraper, Property 16: 指数退避算法
"""

import pytest
import asyncio
import time
from hypothesis import given, strategies as st
from hypothesis import settings

from tencent_video_scraper.rate_limiter import RateLimiter, AdaptiveRateLimiter


def run_async(coro):
    """运行异步协程的辅助函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestRateLimitingCompliance:
    """测试速率限制遵守"""
    
    @given(
        rate=st.floats(min_value=0.1, max_value=10.0),
        request_count=st.integers(min_value=2, max_value=20)
    )
    @settings(max_examples=100, deadline=10000)
    def test_rate_limiting_compliance(self, rate, request_count):
        """
        测试速率限制器确保请求间隔符合配置的限制要求
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        async def _test():
            limiter = RateLimiter(rate)
            
            # 记录请求时间
            request_times = []
            
            # 发送多个请求
            for _ in range(request_count):
                start_time = time.time()
                await limiter.acquire()
                request_times.append(time.time())
            
            # 验证请求间隔符合速率限制
            for i in range(1, len(request_times)):
                time_diff = request_times[i] - request_times[i-1]
                expected_min_interval = 1.0 / rate
                
                # 允许一定的时间误差（50ms）
                assert time_diff >= expected_min_interval - 0.05, \
                    f"请求间隔 {time_diff:.3f}s 小于最小间隔 {expected_min_interval:.3f}s"
        
        run_async(_test())
    
    @given(
        initial_rate=st.floats(min_value=1.0, max_value=5.0),
        new_rate=st.floats(min_value=0.1, max_value=10.0)
    )
    @settings(max_examples=50, deadline=5000)
    def test_dynamic_rate_adjustment_compliance(self, initial_rate, new_rate):
        """
        测试动态速率调整后的速率限制遵守
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        async def _test():
            limiter = RateLimiter(initial_rate)
            
            # 更新速率
            limiter.update_rate(new_rate)
            
            # 发送几个请求测试新速率
            request_times = []
            for _ in range(3):
                await limiter.acquire()
                request_times.append(time.time())
            
            # 验证新速率生效
            if len(request_times) >= 2:
                time_diff = request_times[-1] - request_times[-2]
                expected_min_interval = 1.0 / new_rate
                
                # 允许一定的时间误差
                assert time_diff >= expected_min_interval - 0.05, \
                    f"动态调整后请求间隔 {time_diff:.3f}s 小于预期间隔 {expected_min_interval:.3f}s"
        
        run_async(_test())
    
    @given(rate=st.floats(min_value=0.5, max_value=5.0))
    @settings(max_examples=50, deadline=5000)
    def test_token_bucket_behavior(self, rate):
        """
        测试令牌桶算法的正确行为
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        async def _test():
            limiter = RateLimiter(rate)
            
            # 等待令牌桶填满
            await asyncio.sleep(2.0 / rate)
            
            # 快速消耗所有令牌
            start_time = time.time()
            burst_count = min(int(rate) + 1, 5)  # 限制突发请求数量
            
            for _ in range(burst_count):
                await limiter.acquire()
            
            burst_duration = time.time() - start_time
            
            # 突发请求应该很快完成（令牌桶允许突发）
            assert burst_duration < 1.0, f"突发请求耗时 {burst_duration:.3f}s 过长"
            
            # 后续请求应该受到速率限制
            next_request_start = time.time()
            await limiter.acquire()
            next_request_duration = time.time() - next_request_start
            
            expected_wait = 1.0 / rate
            assert next_request_duration >= expected_wait - 0.05, \
                f"令牌耗尽后等待时间 {next_request_duration:.3f}s 小于预期 {expected_wait:.3f}s"
        
        run_async(_test())


class TestExponentialBackoffAlgorithm:
    """测试指数退避算法"""
    
    @given(
        initial_rate=st.floats(min_value=1.0, max_value=5.0),
        backoff_factor=st.floats(min_value=1.5, max_value=4.0)
    )
    @settings(max_examples=50, deadline=5000)
    def test_exponential_backoff_progression(self, initial_rate, backoff_factor):
        """
        测试指数退避算法逐步增加等待时间
        Feature: tencent-video-scraper, Property 16: 指数退避算法
        """
        async def _test():
            limiter = RateLimiter(initial_rate)
            
            # 记录初始退避因子
            initial_backoff = limiter.backoff_factor
            
            # 触发退避
            limiter.set_backoff(backoff_factor)
            first_backoff = limiter.backoff_factor
            
            # 再次触发退避
            limiter.set_backoff(backoff_factor)
            second_backoff = limiter.backoff_factor
            
            # 验证退避因子递增
            assert first_backoff > initial_backoff, "首次退避因子应该增加"
            assert second_backoff >= first_backoff, "退避因子应该持续增加或保持"
            
            # 验证退避因子不超过最大值
            assert limiter.backoff_factor <= limiter.max_backoff, \
                f"退避因子 {limiter.backoff_factor} 超过最大值 {limiter.max_backoff}"
        
        run_async(_test())
    
    @given(rate=st.floats(min_value=1.0, max_value=5.0))
    @settings(max_examples=50, deadline=10000)
    def test_backoff_affects_wait_time(self, rate):
        """
        测试退避机制影响实际等待时间
        Feature: tencent-video-scraper, Property 16: 指数退避算法
        """
        async def _test():
            limiter = RateLimiter(rate)
            
            # 消耗所有令牌
            await limiter.acquire()
            await limiter.acquire()
            
            # 测量正常等待时间
            start_time = time.time()
            await limiter.acquire()
            normal_wait = time.time() - start_time
            
            # 触发退避
            limiter.trigger_exponential_backoff()
            
            # 再次消耗令牌并测量等待时间
            await limiter.acquire()  # 消耗当前令牌
            
            start_time = time.time()
            await limiter.acquire()
            backoff_wait = time.time() - start_time
            
            # 退避后的等待时间应该更长
            assert backoff_wait > normal_wait, \
                f"退避等待时间 {backoff_wait:.3f}s 应该大于正常等待时间 {normal_wait:.3f}s"
        
        run_async(_test())
    
    @given(rate=st.floats(min_value=1.0, max_value=5.0))
    @settings(max_examples=30, deadline=5000)
    def test_backoff_reset_mechanism(self, rate):
        """
        测试退避重置机制
        Feature: tencent-video-scraper, Property 16: 指数退避算法
        """
        limiter = RateLimiter(rate)
        
        # 触发退避
        limiter.trigger_exponential_backoff()
        backoff_value = limiter.backoff_factor
        
        # 验证退避被触发
        assert backoff_value > 1.0, "退避因子应该大于1"
        
        # 重置退避
        limiter.reset_backoff()
        
        # 验证退避被重置
        assert limiter.backoff_factor == 1.0, "退避因子应该被重置为1"
    
    @given(
        rate=st.floats(min_value=1.0, max_value=5.0),
        backoff_count=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=30, deadline=5000)
    def test_multiple_backoff_triggers(self, rate, backoff_count):
        """
        测试多次触发退避的累积效果
        Feature: tencent-video-scraper, Property 16: 指数退避算法
        """
        limiter = RateLimiter(rate)
        
        previous_backoff = limiter.backoff_factor
        
        # 多次触发退避
        for _ in range(backoff_count):
            limiter.trigger_exponential_backoff()
            current_backoff = limiter.backoff_factor
            
            # 验证退避因子增加或保持（达到最大值时）
            assert current_backoff >= previous_backoff, \
                "退避因子应该递增或保持不变"
            
            # 验证不超过最大值
            assert current_backoff <= limiter.max_backoff, \
                "退避因子不应超过最大值"
            
            previous_backoff = current_backoff


class TestAdaptiveRateLimiter:
    """测试自适应速率限制器"""
    
    @given(
        initial_rate=st.floats(min_value=1.0, max_value=5.0),
        min_rate=st.floats(min_value=0.1, max_value=1.0),
        max_rate=st.floats(min_value=5.0, max_value=10.0)
    )
    @settings(max_examples=30, deadline=5000)
    def test_adaptive_rate_adjustment(self, initial_rate, min_rate, max_rate):
        """
        测试自适应速率调整功能
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        # 确保参数顺序正确
        if min_rate >= initial_rate:
            min_rate = initial_rate * 0.5
        if max_rate <= initial_rate:
            max_rate = initial_rate * 2
        
        limiter = AdaptiveRateLimiter(initial_rate, min_rate, max_rate)
        
        # 记录大量成功请求
        for _ in range(15):
            limiter.record_success()
        
        # 速率应该增加（如果未达到最大值）
        if initial_rate < max_rate:
            assert limiter.rate > initial_rate, "高成功率应该导致速率增加"
        
        # 重置并记录大量失败请求
        limiter = AdaptiveRateLimiter(initial_rate, min_rate, max_rate)
        for _ in range(15):
            limiter.record_failure()
        
        # 速率应该降低（如果未达到最小值）
        if initial_rate > min_rate:
            assert limiter.rate < initial_rate, "高失败率应该导致速率降低"
    
    @given(
        initial_rate=st.floats(min_value=2.0, max_value=5.0),
        success_count=st.integers(min_value=9, max_value=10),
        failure_count=st.integers(min_value=0, max_value=1)
    )
    @settings(max_examples=30, deadline=5000)
    def test_high_success_rate_increases_rate(self, initial_rate, success_count, failure_count):
        """
        测试高成功率导致速率增加
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        max_rate = initial_rate * 2
        limiter = AdaptiveRateLimiter(initial_rate, 0.1, max_rate)
        
        # 记录成功和失败请求
        for _ in range(success_count):
            limiter.record_success()
        for _ in range(failure_count):
            limiter.record_failure()
        
        # 成功率应该很高，速率应该增加
        if initial_rate < max_rate:
            assert limiter.rate >= initial_rate, "高成功率应该维持或增加速率"
    
    @given(
        initial_rate=st.floats(min_value=2.0, max_value=5.0),
        success_count=st.integers(min_value=0, max_value=3),
        failure_count=st.integers(min_value=7, max_value=10)
    )
    @settings(max_examples=30, deadline=5000)
    def test_low_success_rate_decreases_rate(self, initial_rate, success_count, failure_count):
        """
        测试低成功率导致速率降低
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        min_rate = initial_rate * 0.5
        limiter = AdaptiveRateLimiter(initial_rate, min_rate, 10.0)
        
        # 记录成功和失败请求
        for _ in range(success_count):
            limiter.record_success()
        for _ in range(failure_count):
            limiter.record_failure()
        
        # 成功率应该很低，速率应该降低
        if initial_rate > min_rate:
            assert limiter.rate <= initial_rate, "低成功率应该维持或降低速率"


class TestRateLimiterStatistics:
    """测试速率限制器统计功能"""
    
    @given(
        rate=st.floats(min_value=1.0, max_value=5.0),
        request_count=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=50, deadline=10000)
    def test_statistics_accuracy(self, rate, request_count):
        """
        测试统计信息的准确性
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        async def _test():
            limiter = RateLimiter(rate)
            
            # 发送请求
            for _ in range(request_count):
                await limiter.acquire()
            
            stats = limiter.get_stats()
            
            # 验证统计信息
            assert stats['total_requests'] == request_count, \
                f"总请求数应该是 {request_count}，实际是 {stats['total_requests']}"
            
            assert stats['current_rate'] == rate, \
                f"当前速率应该是 {rate}，实际是 {stats['current_rate']}"
            
            assert 0 <= stats['block_rate'] <= 1, \
                f"阻塞率应该在0-1之间，实际是 {stats['block_rate']}"
            
            assert stats['blocked_requests'] >= 0, \
                f"阻塞请求数应该非负，实际是 {stats['blocked_requests']}"
            
            assert stats['backoff_events'] >= 0, \
                f"退避事件数应该非负，实际是 {stats['backoff_events']}"
        
        run_async(_test())
    
    @given(rate=st.floats(min_value=1.0, max_value=5.0))
    @settings(max_examples=30, deadline=5000)
    def test_statistics_reset(self, rate):
        """
        测试统计信息重置功能
        Feature: tencent-video-scraper, Property 7: 速率限制遵守
        """
        limiter = RateLimiter(rate)
        
        # 触发一些统计
        limiter.trigger_exponential_backoff()
        limiter.stats['total_requests'] = 10
        limiter.stats['blocked_requests'] = 5
        
        # 重置统计
        limiter.reset_stats()
        
        stats = limiter.get_stats()
        
        # 验证统计被重置
        assert stats['total_requests'] == 0, "总请求数应该被重置为0"
        assert stats['blocked_requests'] == 0, "阻塞请求数应该被重置为0"
        assert stats['backoff_events'] == 0, "退避事件数应该被重置为0"
        
        # 但当前状态不应该被重置
        assert stats['current_rate'] == rate, "当前速率不应该被重置"
        assert stats['backoff_factor'] > 1.0, "退避因子不应该被重置"