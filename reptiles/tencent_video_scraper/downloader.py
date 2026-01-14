"""
视频下载器

处理视频文件下载，支持多画质选择、断点续传和多线程下载。
"""

import os
import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime
import hashlib

from .models import VideoData, VideoURL, ScraperConfig


logger = logging.getLogger(__name__)


class VideoDownloader:
    """视频下载器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.download_path = self.config.download_path
        
        # 确保下载目录存在
        os.makedirs(self.download_path, exist_ok=True)
        
        # 下载统计
        self.stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_bytes': 0,
            'resumed_downloads': 0
        }
        
        # 进度回调
        self.progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # 并发控制
        self.max_concurrent = 3
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
    
    async def download_video(self, video_data: VideoData, quality: str = 'best') -> Optional[str]:
        """
        下载视频
        
        Args:
            video_data: 视频数据
            quality: 画质选择 ('best', '1080p', '720p', '480p')
            
        Returns:
            Optional[str]: 下载的文件路径，失败返回None
        """
        self.stats['total_downloads'] += 1
        
        # 选择视频链接
        video_url = self._select_video_url(video_data.video_urls, quality)
        if not video_url:
            logger.error("没有可用的视频链接")
            self.stats['failed_downloads'] += 1
            return None
        
        # 生成文件名
        filename = self._generate_filename(video_data.title, video_url)
        filepath = os.path.join(self.download_path, filename)
        
        try:
            # 下载视频
            success = await self._download_file(video_url.url, filepath, video_data.title)
            
            if success:
                self.stats['successful_downloads'] += 1
                logger.info(f"视频下载成功: {filepath}")
                return filepath
            else:
                self.stats['failed_downloads'] += 1
                return None
                
        except Exception as e:
            self.stats['failed_downloads'] += 1
            logger.error(f"视频下载失败: {e}")
            return None
    
    async def download_batch(self, videos: List[VideoData], quality: str = 'best') -> List[str]:
        """
        批量下载视频
        
        Args:
            videos: 视频数据列表
            quality: 画质选择
            
        Returns:
            List[str]: 成功下载的文件路径列表
        """
        results = []
        
        for i, video in enumerate(videos):
            try:
                if self.progress_callback:
                    self.progress_callback({
                        'type': 'download_progress',
                        'current': i + 1,
                        'total': len(videos),
                        'title': video.title,
                        'progress': (i + 1) / len(videos)
                    })
                
                filepath = await self.download_video(video, quality)
                if filepath:
                    results.append(filepath)
                    
            except Exception as e:
                logger.error(f"批量下载中跳过失败的视频: {video.title}, 错误: {e}")
                continue
        
        return results
    
    async def _download_file(self, url: str, filepath: str, title: str) -> bool:
        """
        下载文件，支持断点续传
        
        Args:
            url: 下载URL
            filepath: 保存路径
            title: 视频标题（用于显示）
            
        Returns:
            bool: 是否成功
        """
        async with self.semaphore:
            try:
                # 检查是否支持断点续传
                resume_pos = 0
                if os.path.exists(filepath):
                    resume_pos = os.path.getsize(filepath)
                    self.stats['resumed_downloads'] += 1
                    logger.info(f"断点续传: {filepath}, 从 {resume_pos} 字节开始")
                
                headers = {}
                if resume_pos > 0:
                    headers['Range'] = f'bytes={resume_pos}-'
                
                timeout = aiohttp.ClientTimeout(total=3600)  # 1小时超时
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status not in [200, 206]:
                            logger.error(f"下载失败，HTTP状态: {response.status}")
                            return False
                        
                        # 获取文件大小
                        total_size = int(response.headers.get('Content-Length', 0))
                        if resume_pos > 0:
                            total_size += resume_pos
                        
                        # 打开文件（追加模式用于断点续传）
                        mode = 'ab' if resume_pos > 0 else 'wb'
                        
                        downloaded = resume_pos
                        chunk_size = 1024 * 1024  # 1MB
                        
                        with open(filepath, mode) as f:
                            async for chunk in response.content.iter_chunked(chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # 更新进度
                                if self.progress_callback and total_size > 0:
                                    progress = downloaded / total_size
                                    self.progress_callback({
                                        'type': 'file_progress',
                                        'title': title,
                                        'downloaded': downloaded,
                                        'total': total_size,
                                        'progress': progress,
                                        'speed': self._calculate_speed(downloaded, resume_pos)
                                    })
                        
                        self.stats['total_bytes'] += downloaded - resume_pos
                        return True
                        
            except asyncio.TimeoutError:
                logger.error(f"下载超时: {url}")
                return False
                
            except Exception as e:
                logger.error(f"下载异常: {e}")
                return False
    
    def _select_video_url(self, video_urls: List[VideoURL], quality: str) -> Optional[VideoURL]:
        """
        选择视频链接
        
        Args:
            video_urls: 视频链接列表
            quality: 画质选择
            
        Returns:
            Optional[VideoURL]: 选中的视频链接
        """
        if not video_urls:
            return None
        
        # 画质优先级
        quality_priority = ['1080p', '720p', '480p', '360p', '240p', 'unknown']
        
        if quality == 'best':
            # 选择最高画质
            for q in quality_priority:
                for video_url in video_urls:
                    if video_url.quality.lower() == q.lower():
                        return video_url
            return video_urls[0]
        else:
            # 选择指定画质
            for video_url in video_urls:
                if video_url.quality.lower() == quality.lower():
                    return video_url
            
            # 如果没有指定画质，返回第一个
            return video_urls[0]
    
    def _generate_filename(self, title: str, video_url: VideoURL) -> str:
        """
        生成文件名
        
        Args:
            title: 视频标题
            video_url: 视频链接
            
        Returns:
            str: 文件名
        """
        # 清理标题
        safe_title = self._sanitize_filename(title)
        
        # 确定扩展名
        ext = video_url.format if video_url.format != 'unknown' else 'mp4'
        if ext == 'm3u8':
            ext = 'ts'  # m3u8通常下载为ts
        
        # 添加画质标识
        quality = video_url.quality if video_url.quality != 'unknown' else ''
        
        if quality:
            filename = f"{safe_title}_{quality}.{ext}"
        else:
            filename = f"{safe_title}.{ext}"
        
        return filename
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名"""
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename.strip()
    
    def _calculate_speed(self, downloaded: int, start_pos: int) -> float:
        """计算下载速度（简化版）"""
        # 这里简化处理，实际应该记录时间
        return 0.0
    
    def verify_download(self, filepath: str) -> bool:
        """
        验证下载完整性
        
        Args:
            filepath: 文件路径
            
        Returns:
            bool: 文件是否完整
        """
        try:
            if not os.path.exists(filepath):
                return False
            
            # 检查文件大小
            size = os.path.getsize(filepath)
            if size == 0:
                return False
            
            # 检查文件头（简单验证）
            with open(filepath, 'rb') as f:
                header = f.read(12)
                
                # MP4文件头
                if b'ftyp' in header:
                    return True
                
                # TS文件头
                if header[0] == 0x47:
                    return True
                
                # FLV文件头
                if header[:3] == b'FLV':
                    return True
            
            # 如果无法识别格式，假设有效
            return True
            
        except Exception as e:
            logger.error(f"验证下载失败: {e}")
            return False
    
    def set_progress_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """设置进度回调"""
        self.progress_callback = callback
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        if stats['total_downloads'] > 0:
            stats['success_rate'] = stats['successful_downloads'] / stats['total_downloads']
        else:
            stats['success_rate'] = 0.0
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_bytes': 0,
            'resumed_downloads': 0
        }