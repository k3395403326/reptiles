"""
核心爬虫引擎

整合所有组件，实现完整的腾讯视频爬取功能。
"""

import asyncio
import logging
import time
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
import json

from .models import VideoData, ScraperConfig, BatchReport
from .http_client import HTTPClient
from .parser import VideoParser, VideoURLExtractor, CommentParser
from .svip_handler import SVIPHandler
from .rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


class ScraperEngine:
    """爬虫引擎"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        """
        初始化爬虫引擎
        
        Args:
            config: 爬虫配置
        """
        self.config = config or ScraperConfig()
        
        # 初始化组件
        self.http_client = HTTPClient(self.config)
        self.video_parser = VideoParser()
        self.url_extractor = VideoURLExtractor()
        self.comment_parser = CommentParser()
        self.svip_handler = SVIPHandler(self.config)
        self.rate_limiter = RateLimiter(self.config.rate_limit)
        
        # 统计信息
        self.stats = {
            'total_videos': 0,
            'successful_videos': 0,
            'failed_videos': 0,
            'svip_videos': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
        
        # 错误处理配置
        self.error_handlers = {
            'network_error': self._handle_network_error,
            'parsing_error': self._handle_parsing_error,
            'svip_error': self._handle_svip_error,
            'rate_limit_error': self._handle_rate_limit_error
        }
        
        # 进度回调
        self.progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    async def scrape_video(self, url: str) -> VideoData:
        """
        爬取单个视频的完整信息
        
        Args:
            url: 视频页面URL
            
        Returns:
            VideoData: 爬取的视频数据
            
        Raises:
            Exception: 爬取失败时抛出异常
        """
        self.stats['total_videos'] += 1
        start_time = time.time()
        
        try:
            logger.info(f"开始爬取视频: {url}")
            
            # 速率限制
            await self.rate_limiter.acquire()
            
            # 获取页面内容
            html = await self._fetch_page_content(url)
            
            # 解析基本视频信息
            video_data = self.video_parser.parse_video_info(html, url)
            
            # 提取视频播放链接
            video_urls = self.url_extractor.extract_video_urls(html, url)
            
            # 处理SVIP内容
            if self.svip_handler.is_svip_content(html):
                self.stats['svip_videos'] += 1
                video_data.is_svip = True
                
                # 尝试绕过SVIP限制
                svip_url = await self.svip_handler.bypass_svip_restriction(
                    url, html, self.http_client
                )
                if svip_url:
                    from .models import VideoURL
                    svip_video_url = VideoURL(
                        quality='unknown',
                        url=svip_url,
                        format=self._determine_format(svip_url),
                        size=None,
                        bitrate=None
                    )
                    video_urls.append(svip_video_url)
                    logger.info("SVIP内容绕过成功")
                else:
                    logger.warning("SVIP内容绕过失败")
            
            video_data.video_urls = video_urls
            
            # 提取评论（如果启用）
            if self.config.enable_comments:
                comments = self.comment_parser.parse_comments(
                    html, self.config.max_comments
                )
                video_data.comments = comments
            
            # 验证数据完整性
            self._validate_video_data(video_data)
            
            self.stats['successful_videos'] += 1
            duration = time.time() - start_time
            
            logger.info(f"视频爬取成功: {video_data.title} (耗时: {duration:.2f}s)")
            
            # 调用进度回调
            if self.progress_callback:
                self.progress_callback({
                    'type': 'video_completed',
                    'url': url,
                    'title': video_data.title,
                    'duration': duration,
                    'success': True
                })
            
            return video_data
            
        except Exception as e:
            self.stats['failed_videos'] += 1
            error_info = {
                'url': url,
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                'duration': time.time() - start_time
            }
            self.stats['errors'].append(error_info)
            
            logger.error(f"视频爬取失败: {url}, 错误: {e}")
            
            # 调用进度回调
            if self.progress_callback:
                self.progress_callback({
                    'type': 'video_failed',
                    'url': url,
                    'error': str(e),
                    'duration': time.time() - start_time,
                    'success': False
                })
            
            # 根据错误类型进行处理
            await self._handle_error(e, url)
            
            raise
    
    async def scrape_batch(self, urls: List[str]) -> List[VideoData]:
        """
        批量爬取多个视频
        
        Args:
            urls: 视频URL列表
            
        Returns:
            List[VideoData]: 成功爬取的视频数据列表
        """
        if not urls:
            return []
        
        self.stats['start_time'] = datetime.now()
        logger.info(f"开始批量爬取 {len(urls)} 个视频")
        
        results = []
        
        for i, url in enumerate(urls):
            try:
                # 调用进度回调
                if self.progress_callback:
                    self.progress_callback({
                        'type': 'batch_progress',
                        'current': i + 1,
                        'total': len(urls),
                        'url': url,
                        'progress': (i + 1) / len(urls)
                    })
                
                video_data = await self.scrape_video(url)
                results.append(video_data)
                
            except Exception as e:
                logger.error(f"批量爬取中跳过失败的URL: {url}, 错误: {e}")
                # 继续处理下一个URL
                continue
        
        self.stats['end_time'] = datetime.now()
        
        # 生成批量报告
        report = self._generate_batch_report(urls, results)
        
        logger.info(f"批量爬取完成: 成功 {len(results)}/{len(urls)} 个视频")
        
        # 调用进度回调
        if self.progress_callback:
            self.progress_callback({
                'type': 'batch_completed',
                'total_urls': len(urls),
                'successful_count': len(results),
                'failed_count': len(urls) - len(results),
                'report': report
            })
        
        return results
    
    async def _fetch_page_content(self, url: str) -> str:
        """获取页面内容"""
        try:
            response = await self.http_client.get(url)
            
            if response.status != 200:
                raise Exception(f"HTTP错误: {response.status}")
            
            html = await response.text()
            
            if not html or len(html.strip()) == 0:
                raise Exception("页面内容为空")
            
            return html
            
        except Exception as e:
            await self._handle_error(e, url, 'network_error')
            raise
    
    def _validate_video_data(self, video_data: VideoData):
        """验证视频数据完整性"""
        if not video_data.title or len(video_data.title.strip()) == 0:
            raise ValueError("视频标题不能为空")
        
        if not video_data.url or not video_data.url.startswith('http'):
            raise ValueError("视频URL无效")
        
        if video_data.duration < 0:
            raise ValueError("视频时长不能为负数")
        
        if video_data.view_count < 0:
            raise ValueError("播放量不能为负数")
        
        # 验证视频链接
        if not video_data.video_urls:
            logger.warning("未找到视频播放链接")
        else:
            for video_url in video_data.video_urls:
                if not video_url.url or not video_url.url.startswith('http'):
                    raise ValueError(f"视频播放链接无效: {video_url.url}")
    
    def _determine_format(self, url: str) -> str:
        """确定视频格式"""
        url_lower = url.lower()
        if '.m3u8' in url_lower:
            return 'm3u8'
        elif '.mp4' in url_lower:
            return 'mp4'
        elif '.flv' in url_lower:
            return 'flv'
        return 'unknown'
    
    async def _handle_error(self, error: Exception, url: str, error_type: str = None):
        """处理错误"""
        if error_type and error_type in self.error_handlers:
            await self.error_handlers[error_type](error, url)
        else:
            # 通用错误处理
            logger.error(f"处理URL {url} 时发生错误: {error}")
    
    async def _handle_network_error(self, error: Exception, url: str):
        """处理网络错误"""
        logger.warning(f"网络错误: {error}, URL: {url}")
        
        # 触发退避机制
        self.rate_limiter.trigger_exponential_backoff()
        
        # 如果有代理管理器，尝试切换代理
        if hasattr(self.http_client, 'proxy_manager') and self.http_client.proxy_manager:
            self.http_client.proxy_manager.switch_proxy()
            logger.info("已切换代理服务器")
    
    async def _handle_parsing_error(self, error: Exception, url: str):
        """处理解析错误"""
        logger.warning(f"解析错误: {error}, URL: {url}")
        
        # 记录解析失败的URL，用于后续分析
        self.stats.setdefault('parsing_failures', []).append({
            'url': url,
            'error': str(error),
            'timestamp': datetime.now().isoformat()
        })
    
    async def _handle_svip_error(self, error: Exception, url: str):
        """处理SVIP错误"""
        logger.warning(f"SVIP处理错误: {error}, URL: {url}")
        
        # 记录SVIP处理失败
        self.stats.setdefault('svip_failures', []).append({
            'url': url,
            'error': str(error),
            'timestamp': datetime.now().isoformat()
        })
    
    async def _handle_rate_limit_error(self, error: Exception, url: str):
        """处理速率限制错误"""
        logger.warning(f"速率限制错误: {error}, URL: {url}")
        
        # 增加退避时间
        self.rate_limiter.trigger_exponential_backoff()
        
        # 等待更长时间
        await asyncio.sleep(5)
    
    def _generate_batch_report(self, urls: List[str], results: List[VideoData]) -> BatchReport:
        """生成批量处理报告"""
        total_duration = 0
        if self.stats['start_time'] and self.stats['end_time']:
            total_duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        return BatchReport(
            total_urls=len(urls),
            successful_count=len(results),
            failed_count=len(urls) - len(results),
            svip_count=self.stats['svip_videos'],
            total_duration=total_duration,
            average_duration=total_duration / len(urls) if urls else 0,
            start_time=self.stats['start_time'],
            end_time=self.stats['end_time'],
            errors=self.stats['errors'][:10]  # 只保留前10个错误
        )
    
    def set_progress_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        
        # 添加组件统计
        stats['http_client_stats'] = self.http_client.get_stats()
        stats['parser_stats'] = self.video_parser.get_stats()
        stats['url_extractor_stats'] = self.url_extractor.get_stats()
        stats['comment_parser_stats'] = self.comment_parser.get_stats()
        stats['svip_handler_stats'] = self.svip_handler.get_stats()
        stats['rate_limiter_stats'] = self.rate_limiter.get_stats()
        
        # 计算成功率
        if stats['total_videos'] > 0:
            stats['success_rate'] = stats['successful_videos'] / stats['total_videos']
        else:
            stats['success_rate'] = 0.0
        
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_videos': 0,
            'successful_videos': 0,
            'failed_videos': 0,
            'svip_videos': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
        
        # 重置组件统计
        self.http_client.reset_stats()
        self.video_parser.reset_stats()
        self.url_extractor.reset_stats()
        self.comment_parser.reset_stats()
        self.svip_handler.reset_stats()
        self.rate_limiter.reset_stats()
    
    async def close(self):
        """关闭爬虫引擎，清理资源"""
        try:
            await self.http_client.close()
            logger.info("爬虫引擎已关闭")
        except Exception as e:
            logger.error(f"关闭爬虫引擎时发生错误: {e}")


class AdvancedScraperEngine(ScraperEngine):
    """高级爬虫引擎"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        
        # 使用高级SVIP处理器
        from .svip_handler import AdvancedSVIPHandler
        self.svip_handler = AdvancedSVIPHandler(self.config)
        
        # 添加重试机制
        self.max_retries = self.config.max_retries
        self.retry_delays = [1, 2, 4, 8, 16]  # 指数退避延迟
        
        # 并发控制
        self.max_concurrent = getattr(self.config, 'max_concurrent', 5)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
    
    async def scrape_video_with_retry(self, url: str) -> VideoData:
        """
        带重试机制的视频爬取
        
        Args:
            url: 视频URL
            
        Returns:
            VideoData: 视频数据
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
                    logger.info(f"第 {attempt + 1} 次重试 {url}，等待 {delay} 秒")
                    await asyncio.sleep(delay)
                
                return await self.scrape_video(url)
                
            except Exception as e:
                last_error = e
                logger.warning(f"第 {attempt + 1} 次尝试失败: {url}, 错误: {e}")
                
                if attempt == self.max_retries:
                    break
        
        # 所有重试都失败了
        logger.error(f"所有重试都失败: {url}, 最后错误: {last_error}")
        raise last_error
    
    async def scrape_batch_concurrent(self, urls: List[str]) -> List[VideoData]:
        """
        并发批量爬取
        
        Args:
            urls: 视频URL列表
            
        Returns:
            List[VideoData]: 成功爬取的视频数据列表
        """
        if not urls:
            return []
        
        self.stats['start_time'] = datetime.now()
        logger.info(f"开始并发批量爬取 {len(urls)} 个视频，最大并发数: {self.max_concurrent}")
        
        async def scrape_with_semaphore(url: str) -> Optional[VideoData]:
            async with self.semaphore:
                try:
                    return await self.scrape_video_with_retry(url)
                except Exception as e:
                    logger.error(f"并发爬取失败: {url}, 错误: {e}")
                    return None
        
        # 创建并发任务
        tasks = [scrape_with_semaphore(url) for url in urls]
        
        # 执行并发爬取
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤成功的结果
        successful_results = []
        for result in results:
            if isinstance(result, VideoData):
                successful_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"并发任务异常: {result}")
        
        self.stats['end_time'] = datetime.now()
        
        logger.info(f"并发批量爬取完成: 成功 {len(successful_results)}/{len(urls)} 个视频")
        
        return successful_results
    
    async def scrape_with_progress_tracking(self, urls: List[str]) -> List[VideoData]:
        """
        带进度跟踪的批量爬取
        
        Args:
            urls: 视频URL列表
            
        Returns:
            List[VideoData]: 成功爬取的视频数据列表
        """
        results = []
        total = len(urls)
        
        for i, url in enumerate(urls):
            try:
                # 更新进度
                progress = (i + 1) / total
                logger.info(f"进度: {i + 1}/{total} ({progress:.1%}) - {url}")
                
                if self.progress_callback:
                    self.progress_callback({
                        'type': 'progress_update',
                        'current': i + 1,
                        'total': total,
                        'progress': progress,
                        'url': url
                    })
                
                video_data = await self.scrape_video_with_retry(url)
                results.append(video_data)
                
            except Exception as e:
                logger.error(f"跳过失败的URL: {url}, 错误: {e}")
                continue
        
        return results


class ScraperEngineFactory:
    """爬虫引擎工厂"""
    
    @staticmethod
    def create_engine(engine_type: str = "basic", config: Optional[ScraperConfig] = None) -> ScraperEngine:
        """
        创建爬虫引擎
        
        Args:
            engine_type: 引擎类型 ("basic" 或 "advanced")
            config: 配置对象
            
        Returns:
            ScraperEngine: 爬虫引擎实例
        """
        if engine_type == "advanced":
            return AdvancedScraperEngine(config)
        else:
            return ScraperEngine(config)
    
    @staticmethod
    def create_from_config_file(config_file: str, engine_type: str = "basic") -> ScraperEngine:
        """
        从配置文件创建爬虫引擎
        
        Args:
            config_file: 配置文件路径
            engine_type: 引擎类型
            
        Returns:
            ScraperEngine: 爬虫引擎实例
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            config = ScraperConfig(**config_data)
            return ScraperEngineFactory.create_engine(engine_type, config)
            
        except Exception as e:
            logger.error(f"从配置文件创建引擎失败: {e}")
            raise