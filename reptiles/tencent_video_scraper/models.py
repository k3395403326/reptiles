"""
数据模型定义

定义了爬虫系统中使用的所有数据结构，包括视频数据、配置信息等。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import json


@dataclass
class VideoURL:
    """视频播放链接模型"""
    quality: str  # "1080p", "720p", "480p"
    url: str
    format: str  # "mp4", "m3u8"
    size: Optional[int] = None  # 文件大小（字节）
    bitrate: Optional[int] = None  # 比特率

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "quality": self.quality,
            "url": self.url,
            "format": self.format,
            "size": self.size,
            "bitrate": self.bitrate
        }


@dataclass
class Comment:
    """评论数据模型"""
    content: str
    username: str  # 也可以通过 author 别名访问
    publish_time: Optional[datetime] = None
    likes: int = 0
    replies: int = 0
    
    # 支持 author 作为 username 的别名
    @property
    def author(self) -> str:
        return self.username
    
    def __init__(self, content: str, username: str = None, author: str = None, 
                 publish_time: Optional[datetime] = None, likes: int = 0, replies: int = 0):
        """初始化评论，支持 username 或 author 参数"""
        self.content = content
        self.username = username if username is not None else (author if author is not None else "匿名用户")
        self.publish_time = publish_time
        self.likes = likes
        self.replies = replies

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "content": self.content,
            "username": self.username,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "likes": self.likes,
            "replies": self.replies
        }


@dataclass
class VideoData:
    """视频完整数据模型"""
    url: str
    title: str
    description: str
    duration: int  # 秒
    view_count: int
    publish_time: Optional[datetime]
    video_urls: List[VideoURL]
    comments: List[Comment]
    is_svip: bool
    thumbnail_url: str
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "duration": self.duration,
            "view_count": self.view_count,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "video_urls": [video_url.to_dict() for video_url in self.video_urls],
            "comments": [comment.to_dict() for comment in self.comments],
            "is_svip": self.is_svip,
            "thumbnail_url": self.thumbnail_url,
            "tags": self.tags
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VideoData':
        """从字典创建VideoData实例"""
        video_urls = [VideoURL(**url_data) for url_data in data.get('video_urls', [])]
        comments = []
        for comment_data in data.get('comments', []):
            comment_data['publish_time'] = datetime.fromisoformat(comment_data['publish_time'])
            comments.append(Comment(**comment_data))
        
        data['publish_time'] = datetime.fromisoformat(data['publish_time'])
        data['video_urls'] = video_urls
        data['comments'] = comments
        
        return cls(**data)


@dataclass
class ScraperConfig:
    """爬虫配置模型"""
    rate_limit: float = 1.0  # 每秒请求数
    timeout: int = 30
    max_retries: int = 3
    output_format: str = "json"  # "json", "csv", "xml"
    enable_comments: bool = False
    max_comments: int = 100
    proxies: List[str] = field(default_factory=list)
    user_agents: List[str] = field(default_factory=list)
    enable_download: bool = False
    download_path: str = "./downloads"
    enable_detailed_logs: bool = False
    error_threshold: int = 10  # 错误阈值

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "rate_limit": self.rate_limit,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "output_format": self.output_format,
            "enable_comments": self.enable_comments,
            "max_comments": self.max_comments,
            "proxies": self.proxies,
            "user_agents": self.user_agents,
            "enable_download": self.enable_download,
            "download_path": self.download_path,
            "enable_detailed_logs": self.enable_detailed_logs,
            "error_threshold": self.error_threshold
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScraperConfig':
        """从字典创建ScraperConfig实例"""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'ScraperConfig':
        """从JSON字符串创建ScraperConfig实例"""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class BatchReport:
    """批量任务报告模型"""
    total_urls: int
    successful_count: int
    failed_count: int
    total_duration: float  # 秒
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    svip_count: int = 0
    average_duration: float = 0.0
    failed_urls: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "total_urls": self.total_urls,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "svip_count": self.svip_count,
            "total_duration": self.total_duration,
            "average_duration": self.average_duration,
            "failed_urls": self.failed_urls,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "errors": self.errors,
            "success_rate": self.successful_count / self.total_urls if self.total_urls > 0 else 0
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)