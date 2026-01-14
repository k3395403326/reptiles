"""
腾讯视频爬虫系统

一个功能完整的腾讯视频爬虫工具，支持：
- 视频信息提取
- 视频资源链接获取
- SVIP内容绕过
- 批量处理和下载
- 智能反爬虫处理
"""

__version__ = "1.0.0"
__author__ = "Tencent Video Scraper Team"

from .models import VideoData, VideoURL, ScraperConfig, Comment, BatchReport
from .scraper import ScraperEngine, AdvancedScraperEngine, ScraperEngineFactory
from .http_client import HTTPClient
from .parser import VideoParser, VideoURLExtractor, CommentParser
from .svip_handler import SVIPHandler, AdvancedSVIPHandler
from .rate_limiter import RateLimiter, AdaptiveRateLimiter
from .proxy_manager import ProxyManager
from .storage_manager import StorageManager
from .downloader import VideoDownloader
from .config_manager import ConfigManager, LogManager
from .monitor import MonitorManager, ControlManager, ScraperState
from .third_party_parser import ThirdPartyParserManager, ParserInterface
from .web_service import WebService, create_app

__all__ = [
    # 数据模型
    "VideoData",
    "VideoURL", 
    "ScraperConfig",
    "Comment",
    "BatchReport",
    
    # 爬虫引擎
    "ScraperEngine",
    "AdvancedScraperEngine",
    "ScraperEngineFactory",
    
    # 网络层
    "HTTPClient",
    "ProxyManager",
    "RateLimiter",
    "AdaptiveRateLimiter",
    
    # 解析器
    "VideoParser",
    "VideoURLExtractor",
    "CommentParser",
    
    # SVIP处理
    "SVIPHandler",
    "AdvancedSVIPHandler",
    
    # 第三方解析
    "ThirdPartyParserManager",
    "ParserInterface",
    
    # Web服务
    "WebService",
    "create_app",
    
    # 存储和下载
    "StorageManager",
    "VideoDownloader",
    
    # 配置和日志
    "ConfigManager",
    "LogManager",
    
    # 监控和控制
    "MonitorManager",
    "ControlManager",
    "ScraperState",
]