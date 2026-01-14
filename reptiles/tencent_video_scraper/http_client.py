"""
HTTP客户端

处理网络请求，包括代理管理、请求头伪装等。
"""

import aiohttp
import asyncio
import random
import logging
import time
from typing import Optional, Dict, List, Any

from .models import ScraperConfig
from .proxy_manager import ProxyManager


logger = logging.getLogger(__name__)


class HTTPClient:
    """HTTP客户端，支持异步请求、请求头伪装和重试机制"""
    
    def __init__(self, config: ScraperConfig):
        """初始化HTTP客户端"""
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 初始化代理管理器
        self.proxy_manager = ProxyManager(config.proxies) if config.proxies else None
        
        # 默认User-Agent列表
        self.default_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # 请求统计
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.last_request_time = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            connector = aiohttp.TCPConnector(
                limit=100,  # 连接池大小
                limit_per_host=30,  # 每个主机的连接数
                ttl_dns_cache=300,  # DNS缓存时间
                use_dns_cache=True,
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=self._get_base_headers()
            )
        return self.session
    
    def _get_base_headers(self) -> Dict[str, str]:
        """获取基础请求头"""
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
    
    def _build_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """构建模拟真实浏览器的请求头，支持User-Agent轮换"""
        # 选择User-Agent - 支持配置的User-Agent列表
        if self.config.user_agents:
            user_agent = random.choice(self.config.user_agents)
        else:
            user_agent = random.choice(self.default_user_agents)
        
        headers = self._get_base_headers()
        headers['User-Agent'] = user_agent
        
        # 添加Referer（如果提供）
        if referer:
            headers['Referer'] = referer
        
        # 随机添加一些可选头部
        if random.random() < 0.3:  # 30%概率添加
            headers['Sec-CH-UA'] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
            headers['Sec-CH-UA-Mobile'] = '?0'
            headers['Sec-CH-UA-Platform'] = '"Windows"'
        
        return headers
    
    def _get_proxy(self) -> Optional[str]:
        """获取代理"""
        if self.proxy_manager:
            return self.proxy_manager.get_active_proxy()
        elif self.config.proxies:
            return random.choice(self.config.proxies)
        return None
    
    async def _apply_rate_limit(self):
        """应用速率限制"""
        if self.config.rate_limit > 0:
            min_interval = 1.0 / self.config.rate_limit
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                await asyncio.sleep(sleep_time)
            
            self.last_request_time = time.time()
    
    def _should_retry(self, status_code: int, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.config.max_retries:
            return False
        
        # 5xx服务器错误应该重试
        if 500 <= status_code < 600:
            return True
        
        # 429限流应该重试
        if status_code == 429:
            return True
        
        # 408请求超时应该重试
        if status_code == 408:
            return True
        
        return False
    
    async def _calculate_backoff_delay(self, attempt: int, status_code: int) -> float:
        """计算退避延迟时间"""
        base_delay = 1.0
        
        if status_code == 429:  # 限流
            base_delay = 2.0
        elif 500 <= status_code < 600:  # 服务器错误
            base_delay = 1.5
        
        # 指数退避 + 随机抖动
        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
        return min(delay, 60.0)  # 最大延迟60秒
    
    async def get(self, url: str, referer: Optional[str] = None, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """
        发送GET请求，自动处理代理和重试
        
        Args:
            url: 请求URL
            referer: 引用页面URL
            **kwargs: 额外参数
            
        Returns:
            ClientResponse: 响应对象，失败时返回None
        """
        await self._apply_rate_limit()
        
        session = await self._get_session()
        headers = self._build_headers(referer)
        proxy = self._get_proxy()
        
        # 合并请求头
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers
        
        # 设置代理
        if proxy:
            kwargs['proxy'] = proxy
        
        self.request_count += 1
        
        # 重试机制
        for attempt in range(self.config.max_retries + 1):
            try:
                if self.config.enable_detailed_logs:
                    logger.debug(f"请求 {url} (尝试 {attempt + 1}/{self.config.max_retries + 1})")
                    if proxy:
                        logger.debug(f"使用代理: {proxy}")
                
                async with session.get(url, **kwargs) as response:
                    # 读取响应内容
                    content = await response.text()
                    
                    if response.status == 200:
                        self.success_count += 1
                        # 创建新的响应对象包含内容
                        response._content = content
                        return response
                    
                    # 检查IP封禁
                    if proxy and self.proxy_manager:
                        self.proxy_manager.handle_ip_ban_detection(proxy, content, response.status)
                    
                    # 检查是否应该重试
                    if self._should_retry(response.status, attempt):
                        delay = await self._calculate_backoff_delay(attempt, response.status)
                        logger.warning(f"HTTP {response.status}，等待 {delay:.1f} 秒后重试")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(f"HTTP错误 {response.status}: {url}")
                        self.error_count += 1
                        return None
                        
            except asyncio.TimeoutError:
                logger.warning(f"请求超时 (尝试 {attempt + 1}): {url}")
                if attempt < self.config.max_retries:
                    delay = await self._calculate_backoff_delay(attempt, 408)
                    await asyncio.sleep(delay)
                else:
                    self.error_count += 1
                    
            except aiohttp.ClientError as e:
                logger.warning(f"网络错误 (尝试 {attempt + 1}): {str(e)}")
                
                # 标记代理失败
                if proxy and self.proxy_manager:
                    self.proxy_manager.mark_proxy_failed(proxy)
                
                if attempt < self.config.max_retries:
                    delay = await self._calculate_backoff_delay(attempt, 500)
                    await asyncio.sleep(delay)
                else:
                    self.error_count += 1
                    
            except Exception as e:
                logger.error(f"未知错误: {str(e)}")
                self.error_count += 1
                break
        
        logger.error(f"请求失败，已达到最大重试次数: {url}")
        return None
    
    async def post(self, url: str, referer: Optional[str] = None, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """发送POST请求"""
        await self._apply_rate_limit()
        
        session = await self._get_session()
        headers = self._build_headers(referer)
        proxy = self._get_proxy()
        
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers
        
        if proxy:
            kwargs['proxy'] = proxy
        
        self.request_count += 1
        
        try:
            async with session.post(url, **kwargs) as response:
                content = await response.text()
                if response.status == 200:
                    self.success_count += 1
                    response._content = content
                    return response
                else:
                    logger.warning(f"POST请求失败 {response.status}: {url}")
                    self.error_count += 1
                    
        except Exception as e:
            logger.error(f"POST请求异常: {str(e)}")
            self.error_count += 1
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取请求统计信息"""
        return {
            'total_requests': self.request_count,
            'successful_requests': self.success_count,
            'failed_requests': self.error_count,
            'success_rate': self.success_count / self.request_count if self.request_count > 0 else 0
        }
    
    def reset_stats(self):
        """重置请求统计信息"""
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.last_request_time = 0
    
    async def close(self):
        """关闭会话"""
        if self.proxy_manager:
            await self.proxy_manager.stop_health_check()
            
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("HTTP会话已关闭")
    
    async def start(self):
        """启动HTTP客户端"""
        if self.proxy_manager:
            await self.proxy_manager.start_health_check()
            logger.info("代理健康检查已启动")