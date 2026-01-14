"""
速率限制器

实现令牌桶算法和指数退避机制，控制请求频率。
"""

import asyncio
import time
import logging
from typing import Optional


logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, requests_per_second: float):
        """
        初始化速率限制器
        
        Args:
            requests_per_second: 每秒允许的请求数
        """
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.time()
        self.backoff_factor = 1.0
        self.max_backoff = 60.0  # 最大退避时间（秒）
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'backoff_events': 0
        }
    
    async def acquire(self):
        """
        获取请求令牌，实现令牌桶算法
        """
        self.stats['total_requests'] += 1
        
        # 更新令牌桶
        now = time.time()
        time_passed = now - self.last_update
        self.last_update = now
        
        # 添加新令牌
        self.tokens = min(self.rate, self.tokens + time_passed * self.rate)
        
        if self.tokens >= 1.0:
            # 有可用令牌，消费一个
            self.tokens -= 1.0
            # 重置退避因子
            if self.backoff_factor > 1.0:
                self.backoff_factor = max(1.0, self.backoff_factor * 0.9)
        else:
            # 没有可用令牌，需要等待
            self.stats['blocked_requests'] += 1
            wait_time = (1.0 - self.tokens) / self.rate * self.backoff_factor
            
            logger.debug(f"速率限制触发，等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)
            
            # 等待后，更新时间并消费令牌
            now = time.time()
            time_passed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.rate, self.tokens + time_passed * self.rate)
            self.tokens -= 1.0  # 消费一个令牌
    
    def set_backoff(self, factor: float):
        """
        设置退避因子
        
        Args:
            factor: 退避倍数
        """
        old_factor = self.backoff_factor
        self.backoff_factor = min(self.max_backoff, self.backoff_factor * factor)
        
        if self.backoff_factor > old_factor:
            self.stats['backoff_events'] += 1
            logger.info(f"触发退避机制，退避因子: {old_factor:.2f} -> {self.backoff_factor:.2f}")
    
    def trigger_exponential_backoff(self):
        """触发指数退避"""
        self.set_backoff(2.0)
    
    def reset_backoff(self):
        """重置退避因子"""
        if self.backoff_factor > 1.0:
            logger.info(f"重置退避因子: {self.backoff_factor:.2f} -> 1.0")
            self.backoff_factor = 1.0
    
    def update_rate(self, new_rate: float):
        """
        更新请求速率
        
        Args:
            new_rate: 新的每秒请求数
        """
        old_rate = self.rate
        self.rate = new_rate
        
        # 调整令牌数量
        if new_rate > old_rate:
            # 速率增加，增加令牌
            self.tokens = min(new_rate, self.tokens * (new_rate / old_rate))
        else:
            # 速率减少，减少令牌
            self.tokens = min(new_rate, self.tokens)
        
        logger.info(f"更新请求速率: {old_rate} -> {new_rate} 请求/秒")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self.stats.copy()
        stats.update({
            'current_rate': self.rate,
            'current_tokens': self.tokens,
            'backoff_factor': self.backoff_factor,
            'block_rate': stats['blocked_requests'] / stats['total_requests'] if stats['total_requests'] > 0 else 0
        })
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'backoff_events': 0
        }


class AdaptiveRateLimiter(RateLimiter):
    """自适应速率限制器"""
    
    def __init__(self, initial_rate: float, min_rate: float = 0.1, max_rate: float = 10.0):
        """
        初始化自适应速率限制器
        
        Args:
            initial_rate: 初始请求速率
            min_rate: 最小请求速率
            max_rate: 最大请求速率
        """
        super().__init__(initial_rate)
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.success_count = 0
        self.failure_count = 0
        self.adjustment_threshold = 10  # 调整阈值
    
    def record_success(self):
        """记录成功请求"""
        self.success_count += 1
        self._check_adjustment()
    
    def record_failure(self):
        """记录失败请求"""
        self.failure_count += 1
        self._check_adjustment()
    
    def _check_adjustment(self):
        """检查是否需要调整速率"""
        total_requests = self.success_count + self.failure_count
        
        if total_requests >= self.adjustment_threshold:
            success_rate = self.success_count / total_requests
            
            if success_rate > 0.9:
                # 成功率高，可以增加速率
                new_rate = min(self.max_rate, self.rate * 1.2)
                if new_rate != self.rate:
                    self.update_rate(new_rate)
                    logger.info(f"成功率高({success_rate:.2f})，增加请求速率")
            elif success_rate < 0.7:
                # 成功率低，需要降低速率
                new_rate = max(self.min_rate, self.rate * 0.8)
                if new_rate != self.rate:
                    self.update_rate(new_rate)
                    logger.info(f"成功率低({success_rate:.2f})，降低请求速率")
            
            # 重置计数器
            self.success_count = 0
            self.failure_count = 0