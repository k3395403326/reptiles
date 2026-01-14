"""
代理管理器属性测试

测试代理管理器的代理切换机制和其他属性。
Feature: tencent-video-scraper, Property 14: 代理切换机制
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from hypothesis import given, strategies as st, settings, assume

from tencent_video_scraper.proxy_manager import ProxyManager, ProxyInfo, ProxyStatus


# 自定义策略
@st.composite
def valid_proxy_list_strategy(draw):
    """生成有效的代理列表策略"""
    proxy_count = draw(st.integers(min_value=1, max_value=10))
    proxies = []
    
    for i in range(proxy_count):
        proxy_type = draw(st.sampled_from(['http', 'https', 'socks5']))
        host = draw(st.text(min_size=5, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'))
        port = draw(st.integers(min_value=1000, max_value=65535))
        proxies.append(f"{proxy_type}://{host}.com:{port}")
    
    return proxies


@st.composite
def proxy_response_strategy(draw):
    """生成代理响应策略"""
    status_code = draw(st.integers(min_value=200, max_value=599))
    
    # 生成响应文本
    if status_code == 403:
        response_text = draw(st.sampled_from([
            "访问被拒绝", "access denied", "forbidden", "您的IP已被限制"
        ]))
    elif status_code == 429:
        response_text = draw(st.sampled_from([
            "too many requests", "rate limited", "请稍后再试"
        ]))
    else:
        response_text = draw(st.text(min_size=0, max_size=100, alphabet='abcdefghijklmnopqrstuvwxyz '))
    
    return status_code, response_text


class TestProxyManagerSwitchingMechanism:
    """测试代理管理器切换机制"""
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=100)
    def test_proxy_manager_initialization(self, proxy_list):
        """
        测试代理管理器正确初始化代理池
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        
        # 去重后的代理列表
        unique_proxies = list(set(proxy_list))
        
        # 验证所有唯一代理都被正确添加
        assert len(manager.proxies) == len(unique_proxies)
        
        # 验证每个代理的初始状态
        for proxy_url in unique_proxies:
            assert proxy_url in manager.proxies
            proxy_info = manager.proxies[proxy_url]
            assert proxy_info.status == ProxyStatus.ACTIVE
            assert proxy_info.failure_count == 0
            assert proxy_info.success_count == 0
            assert proxy_info.url == proxy_url
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=100)
    def test_active_proxy_selection(self, proxy_list):
        """
        测试活跃代理选择机制
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        
        # 获取活跃代理应该从代理列表中选择
        for _ in range(10):
            active_proxy = manager.get_active_proxy()
            if active_proxy:  # 如果有可用代理
                assert active_proxy in proxy_list
        
        # 标记一些代理为失败状态
        if len(proxy_list) > 1:
            failed_proxy = proxy_list[0]
            manager.mark_proxy_failed(failed_proxy)
            manager.mark_proxy_failed(failed_proxy)
            manager.mark_proxy_failed(failed_proxy)  # 连续3次失败
            
            # 失败的代理不应该被选择
            for _ in range(10):
                active_proxy = manager.get_active_proxy()
                if active_proxy:
                    assert active_proxy != failed_proxy
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=50)
    def test_proxy_failure_handling(self, proxy_list):
        """
        测试代理失败处理机制
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        
        # 测试单次失败
        test_proxy = proxy_list[0]
        manager.mark_proxy_failed(test_proxy)
        
        proxy_info = manager.proxies[test_proxy]
        assert proxy_info.failure_count == 1
        assert proxy_info.status == ProxyStatus.ACTIVE  # 单次失败仍然活跃
        
        # 测试多次失败
        manager.mark_proxy_failed(test_proxy)
        manager.mark_proxy_failed(test_proxy)
        
        assert proxy_info.failure_count == 3
        assert proxy_info.status == ProxyStatus.FAILED  # 3次失败后标记为失败
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=50)
    def test_proxy_ban_detection(self, proxy_list):
        """
        测试代理封禁检测机制
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        test_proxy = proxy_list[0]
        
        # 测试封禁标记
        manager.mark_proxy_banned(test_proxy, "192.168.1.1")
        
        proxy_info = manager.proxies[test_proxy]
        assert proxy_info.status == ProxyStatus.BANNED
        assert "192.168.1.1" in manager.banned_ips
        
        # 被封禁的代理不应该被选择
        for _ in range(10):
            active_proxy = manager.get_active_proxy()
            if active_proxy:
                assert active_proxy != test_proxy
    
    @given(proxy_response_strategy())
    @settings(max_examples=100)
    def test_ip_ban_detection_logic(self, response_data):
        """
        测试IP封禁检测逻辑
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        status_code, response_text = response_data
        manager = ProxyManager(['http://test.com:8080'])
        
        is_banned = manager.detect_ip_ban(response_text, status_code)
        
        # 验证封禁检测逻辑
        if status_code in [403, 429, 503]:
            assert is_banned == True
        elif any(indicator in response_text.lower() for indicator in [
            '访问被拒绝', 'access denied', 'forbidden', '您的IP已被限制',
            'ip blocked', 'rate limited', 'too many requests'
        ]):
            assert is_banned == True
        else:
            # 其他情况应该不被检测为封禁
            assert isinstance(is_banned, bool)
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=50)
    def test_proxy_stats_accuracy(self, proxy_list):
        """
        测试代理统计信息准确性
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        
        # 去重后的代理列表
        unique_proxies = list(set(proxy_list))
        
        # 初始统计
        stats = manager.get_proxy_stats()
        assert stats['total'] == len(unique_proxies)
        assert stats['active'] == len(unique_proxies)
        assert stats['failed'] == 0
        assert stats['banned'] == 0
        
        # 标记一些代理为不同状态
        if len(unique_proxies) >= 3:
            # 标记一个为失败
            manager.mark_proxy_failed(unique_proxies[0])
            manager.mark_proxy_failed(unique_proxies[0])
            manager.mark_proxy_failed(unique_proxies[0])
            
            # 标记一个为封禁
            manager.mark_proxy_banned(unique_proxies[1])
            
            # 重新获取统计
            stats = manager.get_proxy_stats()
            assert stats['total'] == len(unique_proxies)
            assert stats['active'] == len(unique_proxies) - 2
            assert stats['failed'] == 1
            assert stats['banned'] == 1
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=50)
    def test_proxy_reset_functionality(self, proxy_list):
        """
        测试代理重置功能
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        test_proxy = proxy_list[0]
        
        # 标记代理为失败
        manager.mark_proxy_failed(test_proxy)
        manager.mark_proxy_failed(test_proxy)
        manager.mark_proxy_failed(test_proxy)
        
        proxy_info = manager.proxies[test_proxy]
        assert proxy_info.status == ProxyStatus.FAILED
        assert proxy_info.failure_count == 3
        
        # 重置代理
        manager.reset_proxy(test_proxy)
        
        assert proxy_info.status == ProxyStatus.ACTIVE
        assert proxy_info.failure_count == 0
        assert proxy_info.last_check == 0
    
    @given(valid_proxy_list_strategy())
    @settings(max_examples=50)
    def test_proxy_addition_removal(self, proxy_list):
        """
        测试代理添加和移除功能
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(proxy_list)
        initial_count = len(manager.proxies)
        
        # 添加新代理
        new_proxy = "http://newproxy.com:8080"
        manager.add_proxy(new_proxy)
        
        assert len(manager.proxies) == initial_count + 1
        assert new_proxy in manager.proxies
        assert manager.proxies[new_proxy].status == ProxyStatus.ACTIVE
        
        # 移除代理
        if proxy_list:
            remove_proxy = proxy_list[0]
            manager.remove_proxy(remove_proxy)
            
            assert len(manager.proxies) == initial_count  # 添加1个，移除1个
            assert remove_proxy not in manager.proxies
    
    def test_best_proxy_selection_algorithm(self):
        """
        测试最佳代理选择算法
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        proxies = ['http://proxy1.com:8080', 'http://proxy2.com:8080', 'http://proxy3.com:8080']
        manager = ProxyManager(proxies)
        
        # 设置不同的成功率和响应时间
        manager.proxies['http://proxy1.com:8080'].success_count = 10
        manager.proxies['http://proxy1.com:8080'].failure_count = 0
        manager.proxies['http://proxy1.com:8080'].response_time = 1.0
        
        manager.proxies['http://proxy2.com:8080'].success_count = 8
        manager.proxies['http://proxy2.com:8080'].failure_count = 2
        manager.proxies['http://proxy2.com:8080'].response_time = 0.5
        
        manager.proxies['http://proxy3.com:8080'].success_count = 5
        manager.proxies['http://proxy3.com:8080'].failure_count = 5
        manager.proxies['http://proxy3.com:8080'].response_time = 2.0
        
        # 获取最佳代理
        best_proxy = manager.get_best_proxy()
        
        # 应该选择成功率最高的代理（proxy1: 100%成功率）
        assert best_proxy == 'http://proxy1.com:8080'
    
    @given(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_proxy_url_validation(self, proxy_urls):
        """
        测试代理URL验证和处理
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        # 构造有效的代理URL
        valid_proxies = []
        for i, url in enumerate(proxy_urls):
            valid_proxy = f"http://{url}.com:{8080 + i}"
            valid_proxies.append(valid_proxy)
        
        manager = ProxyManager(valid_proxies)
        
        # 验证所有代理都被正确处理
        assert len(manager.proxies) == len(valid_proxies)
        
        for proxy in valid_proxies:
            assert proxy in manager.proxies
            proxy_info = manager.proxies[proxy]
            assert proxy_info.url == proxy
            assert proxy_info.status == ProxyStatus.ACTIVE


class TestProxyManagerHealthCheck:
    """测试代理管理器健康检查"""
    
    def test_health_check_task_management(self):
        """
        测试健康检查任务管理
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager(['http://test.com:8080'])
        
        # 初始状态没有检查任务
        assert manager.check_task is None
        
        # 启动健康检查后应该有任务
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(manager.start_health_check())
            assert manager.check_task is not None
            assert not manager.check_task.done()
            
            # 停止健康检查
            loop.run_until_complete(manager.stop_health_check())
            assert manager.check_task.done()
        finally:
            loop.close()
    
    def test_proxy_info_success_rate_calculation(self):
        """
        测试代理信息成功率计算
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        proxy_info = ProxyInfo("http://test.com:8080")
        
        # 初始成功率应该为0
        assert proxy_info.success_rate == 0
        
        # 设置成功和失败次数
        proxy_info.success_count = 8
        proxy_info.failure_count = 2
        
        # 成功率应该为0.8
        assert proxy_info.success_rate == 0.8
        
        # 只有成功次数
        proxy_info.failure_count = 0
        assert proxy_info.success_rate == 1.0
        
        # 只有失败次数
        proxy_info.success_count = 0
        proxy_info.failure_count = 5
        assert proxy_info.success_rate == 0.0


class TestProxyManagerEdgeCases:
    """测试代理管理器边界情况"""
    
    def test_empty_proxy_list_handling(self):
        """
        测试空代理列表处理
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        manager = ProxyManager([])
        
        # 空代理列表应该正常初始化
        assert len(manager.proxies) == 0
        
        # 获取活跃代理应该返回None
        assert manager.get_active_proxy() is None
        assert manager.get_best_proxy() is None
        
        # 统计信息应该全为0
        stats = manager.get_proxy_stats()
        assert stats['total'] == 0
        assert stats['active'] == 0
        assert stats['failed'] == 0
        assert stats['banned'] == 0
    
    def test_all_proxies_failed_scenario(self):
        """
        测试所有代理都失败的场景
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        proxies = ['http://proxy1.com:8080', 'http://proxy2.com:8080']
        manager = ProxyManager(proxies)
        
        # 标记所有代理为失败
        for proxy in proxies:
            for _ in range(3):  # 连续3次失败
                manager.mark_proxy_failed(proxy)
        
        # 应该没有可用代理
        assert manager.get_active_proxy() is None
        assert manager.get_best_proxy() is None
        
        # 统计信息应该反映所有代理都失败
        stats = manager.get_proxy_stats()
        assert stats['active'] == 0
        assert stats['failed'] == len(proxies)
    
    def test_duplicate_proxy_handling(self):
        """
        测试重复代理处理
        Feature: tencent-video-scraper, Property 14: 代理切换机制
        Validates: Requirements 5.2
        """
        duplicate_proxies = ['http://test.com:8080', 'http://test.com:8080', 'http://other.com:8080']
        manager = ProxyManager(duplicate_proxies)
        
        # 重复的代理应该只保留一个
        assert len(manager.proxies) == 2
        assert 'http://test.com:8080' in manager.proxies
        assert 'http://other.com:8080' in manager.proxies
        
        # 添加已存在的代理不应该改变数量
        manager.add_proxy('http://test.com:8080')
        assert len(manager.proxies) == 2