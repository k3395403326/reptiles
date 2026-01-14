"""
代理管理器

管理代理池，实现代理健康检查和自动切换。
"""

import asyncio
import aiohttp
import logging
import time
import random
from typing import List, Optional, Dict, Set
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)


class ProxyStatus(Enum):
    """代理状态枚举"""
    ACTIVE = "active"
    FAILED = "failed"
    BANNED = "banned"
    CHECKING = "checking"


@dataclass
class ProxyInfo:
    """代理信息"""
    url: str
    status: ProxyStatus = ProxyStatus.ACTIVE
    last_check: float = 0
    failure_count: int = 0
    success_count: int = 0
    response_time: float = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0


class ProxyManager:
    """代理管理器"""
    
    def __init__(self, proxies: List[str], check_interval: int = 300):
        """
        初始化代理管理器
        
        Args:
            proxies: 代理URL列表
            check_interval: 健康检查间隔（秒）
        """
        self.proxies: Dict[str, ProxyInfo] = {
            proxy: ProxyInfo(proxy) for proxy in proxies
        }
        self.check_interval = check_interval
        self.banned_ips: Set[str] = set()
        self.current_proxy_index = 0
        self.check_task: Optional[asyncio.Task] = None
        
        # 测试URL列表
        self.test_urls = [
            'http://httpbin.org/ip',
            'https://api.ipify.org?format=json',
            'http://ip-api.com/json'
        ]
    
    async def start_health_check(self):
        """启动健康检查任务"""
        if self.check_task is None or self.check_task.done():
            self.check_task = asyncio.create_task(self._health_check_loop())
            logger.info("代理健康检查任务已启动")
    
    async def stop_health_check(self):
        """停止健康检查任务"""
        if self.check_task and not self.check_task.done():
            self.check_task.cancel()
            try:
                await self.check_task
            except asyncio.CancelledError:
                pass
            logger.info("代理健康检查任务已停止")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self._check_all_proxies()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")
                await asyncio.sleep(60)  # 出错时等待1分钟
    
    async def _check_all_proxies(self):
        """检查所有代理"""
        tasks = []
        for proxy_info in self.proxies.values():
            if time.time() - proxy_info.last_check > self.check_interval:
                tasks.append(self._check_proxy(proxy_info))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_proxy(self, proxy_info: ProxyInfo):
        """检查单个代理"""
        proxy_info.status = ProxyStatus.CHECKING
        proxy_info.last_check = time.time()
        
        test_url = random.choice(self.test_urls)
        start_time = time.time()
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, proxy=proxy_info.url) as response:
                    if response.status == 200:
                        proxy_info.response_time = time.time() - start_time
                        proxy_info.success_count += 1
                        proxy_info.failure_count = 0  # 重置失败计数
                        proxy_info.status = ProxyStatus.ACTIVE
                        logger.debug(f"代理检查成功: {proxy_info.url}")
                    else:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
                        
        except Exception as e:
            proxy_info.failure_count += 1
            proxy_info.response_time = time.time() - start_time
            
            # 连续失败3次标记为失败
            if proxy_info.failure_count >= 3:
                proxy_info.status = ProxyStatus.FAILED
                logger.warning(f"代理标记为失败: {proxy_info.url} - {e}")
            else:
                proxy_info.status = ProxyStatus.ACTIVE
                logger.debug(f"代理检查失败: {proxy_info.url} - {e}")
    
    def get_active_proxy(self) -> Optional[str]:
        """获取可用代理"""
        active_proxies = [
            proxy_info for proxy_info in self.proxies.values()
            if proxy_info.status == ProxyStatus.ACTIVE
        ]
        
        if not active_proxies:
            logger.warning("没有可用的代理")
            return None
        
        # 按成功率和响应时间排序
        active_proxies.sort(
            key=lambda p: (p.success_rate, -p.response_time),
            reverse=True
        )
        
        # 轮询选择前50%的代理
        top_proxies = active_proxies[:max(1, len(active_proxies) // 2)]
        selected = random.choice(top_proxies)
        
        return selected.url
    
    def mark_proxy_banned(self, proxy_url: str, ip: Optional[str] = None):
        """标记代理被封禁"""
        if proxy_url in self.proxies:
            self.proxies[proxy_url].status = ProxyStatus.BANNED
            logger.warning(f"代理被标记为封禁: {proxy_url}")
        
        if ip:
            self.banned_ips.add(ip)
            logger.warning(f"IP被标记为封禁: {ip}")
    
    def mark_proxy_failed(self, proxy_url: str):
        """标记代理失败"""
        if proxy_url in self.proxies:
            proxy_info = self.proxies[proxy_url]
            proxy_info.failure_count += 1
            
            if proxy_info.failure_count >= 3:
                proxy_info.status = ProxyStatus.FAILED
                logger.warning(f"代理因多次失败被标记为失败: {proxy_url}")
    
    def get_proxy_stats(self) -> Dict[str, int]:
        """获取代理统计信息"""
        stats = {
            'total': len(self.proxies),
            'active': 0,
            'failed': 0,
            'banned': 0,
            'checking': 0
        }
        
        for proxy_info in self.proxies.values():
            if proxy_info.status == ProxyStatus.ACTIVE:
                stats['active'] += 1
            elif proxy_info.status == ProxyStatus.FAILED:
                stats['failed'] += 1
            elif proxy_info.status == ProxyStatus.BANNED:
                stats['banned'] += 1
            elif proxy_info.status == ProxyStatus.CHECKING:
                stats['checking'] += 1
        
        return stats
    
    def reset_proxy(self, proxy_url: str):
        """重置代理状态"""
        if proxy_url in self.proxies:
            proxy_info = self.proxies[proxy_url]
            proxy_info.status = ProxyStatus.ACTIVE
            proxy_info.failure_count = 0
            proxy_info.last_check = 0
            logger.info(f"代理状态已重置: {proxy_url}")
    
    def add_proxy(self, proxy_url: str):
        """添加新代理"""
        if proxy_url not in self.proxies:
            self.proxies[proxy_url] = ProxyInfo(proxy_url)
            logger.info(f"添加新代理: {proxy_url}")
    
    def detect_ip_ban(self, response_text: str, status_code: int) -> bool:
        """
        检测IP是否被封禁
        
        Args:
            response_text: 响应文本
            status_code: HTTP状态码
            
        Returns:
            bool: 是否被封禁
        """
        # 常见的封禁指示器
        ban_indicators = [
            '访问被拒绝', '访问受限', 'access denied', 'forbidden',
            '您的IP已被限制', 'ip blocked', 'ip banned',
            '请稍后再试', 'rate limited', 'too many requests',
            '验证码', 'captcha', 'verification required'
        ]
        
        # 检查状态码
        if status_code in [403, 429, 503]:
            return True
        
        # 检查响应文本
        if response_text:
            response_lower = response_text.lower()
            for indicator in ban_indicators:
                if indicator in response_lower:
                    return True
        
        return False
    
    def handle_ip_ban_detection(self, proxy_url: str, response_text: str, status_code: int):
        """
        处理IP封禁检测
        
        Args:
            proxy_url: 代理URL
            response_text: 响应文本
            status_code: HTTP状态码
        """
        if self.detect_ip_ban(response_text, status_code):
            self.mark_proxy_banned(proxy_url)
            logger.warning(f"检测到IP封禁，代理已被标记: {proxy_url}")
    
    def get_best_proxy(self) -> Optional[str]:
        """
        获取最佳代理（基于成功率和响应时间）
        
        Returns:
            str: 最佳代理URL，如果没有可用代理返回None
        """
        active_proxies = [
            proxy_info for proxy_info in self.proxies.values()
            if proxy_info.status == ProxyStatus.ACTIVE
        ]
        
        if not active_proxies:
            return None
        
        # 计算综合评分：成功率 * 0.7 + (1 - 响应时间/最大响应时间) * 0.3
        max_response_time = max(p.response_time for p in active_proxies) or 1
        
        for proxy in active_proxies:
            response_score = 1 - (proxy.response_time / max_response_time)
            proxy.score = proxy.success_rate * 0.7 + response_score * 0.3
        
        # 选择评分最高的代理
        best_proxy = max(active_proxies, key=lambda p: p.score)
        return best_proxy.url
    
    def remove_proxy(self, proxy_url: str):
        """移除代理"""
        if proxy_url in self.proxies:
            del self.proxies[proxy_url]
            logger.info(f"移除代理: {proxy_url}")