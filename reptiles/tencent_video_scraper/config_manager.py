"""
配置管理器

处理配置加载、验证和默认值处理。
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import asdict

from .models import ScraperConfig


logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器"""
    
    DEFAULT_CONFIG = {
        'rate_limit': 1.0,
        'timeout': 30,
        'max_retries': 3,
        'output_format': 'json',
        'enable_comments': False,
        'max_comments': 100,
        'proxies': [],
        'user_agents': [],
        'enable_download': False,
        'download_path': './downloads',
        'enable_detailed_logs': False,
        'error_threshold': 10
    }
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.config: Optional[ScraperConfig] = None
        
        if config_file and os.path.exists(config_file):
            self.load_from_file(config_file)
        else:
            self.config = ScraperConfig()
    
    def load_from_file(self, filepath: str) -> ScraperConfig:
        """
        从文件加载配置
        
        Args:
            filepath: 配置文件路径
            
        Returns:
            ScraperConfig: 配置对象
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 合并默认配置
            merged_data = self.DEFAULT_CONFIG.copy()
            merged_data.update(data)
            
            # 验证配置
            validated_data = self._validate_config(merged_data)
            
            self.config = ScraperConfig(**validated_data)
            self.config_file = filepath
            
            logger.info(f"配置已从文件加载: {filepath}")
            return self.config
            
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            raise ValueError(f"配置文件格式错误: {e}")
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    def load_from_dict(self, data: Dict[str, Any]) -> ScraperConfig:
        """
        从字典加载配置
        
        Args:
            data: 配置字典
            
        Returns:
            ScraperConfig: 配置对象
        """
        # 合并默认配置
        merged_data = self.DEFAULT_CONFIG.copy()
        merged_data.update(data)
        
        # 验证配置
        validated_data = self._validate_config(merged_data)
        
        self.config = ScraperConfig(**validated_data)
        return self.config
    
    def save_to_file(self, filepath: Optional[str] = None) -> str:
        """
        保存配置到文件
        
        Args:
            filepath: 文件路径（可选）
            
        Returns:
            str: 保存的文件路径
        """
        if not filepath:
            filepath = self.config_file or 'config.json'
        
        if not self.config:
            self.config = ScraperConfig()
        
        try:
            data = self.config.to_dict()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.config_file = filepath
            logger.info(f"配置已保存到文件: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise
    
    def _validate_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证配置数据
        
        Args:
            data: 配置数据
            
        Returns:
            Dict[str, Any]: 验证后的配置数据
        """
        validated = {}
        
        # 验证速率限制
        rate_limit = data.get('rate_limit', self.DEFAULT_CONFIG['rate_limit'])
        if not isinstance(rate_limit, (int, float)) or rate_limit <= 0:
            logger.warning(f"无效的速率限制: {rate_limit}，使用默认值")
            rate_limit = self.DEFAULT_CONFIG['rate_limit']
        validated['rate_limit'] = float(rate_limit)
        
        # 验证超时时间
        timeout = data.get('timeout', self.DEFAULT_CONFIG['timeout'])
        if not isinstance(timeout, int) or timeout <= 0:
            logger.warning(f"无效的超时时间: {timeout}，使用默认值")
            timeout = self.DEFAULT_CONFIG['timeout']
        validated['timeout'] = int(timeout)
        
        # 验证重试次数
        max_retries = data.get('max_retries', self.DEFAULT_CONFIG['max_retries'])
        if not isinstance(max_retries, int) or max_retries < 0:
            logger.warning(f"无效的重试次数: {max_retries}，使用默认值")
            max_retries = self.DEFAULT_CONFIG['max_retries']
        validated['max_retries'] = int(max_retries)
        
        # 验证输出格式
        output_format = data.get('output_format', self.DEFAULT_CONFIG['output_format'])
        valid_formats = ['json', 'csv', 'xml']
        if output_format.lower() not in valid_formats:
            logger.warning(f"无效的输出格式: {output_format}，使用默认值")
            output_format = self.DEFAULT_CONFIG['output_format']
        validated['output_format'] = output_format.lower()
        
        # 验证布尔值
        validated['enable_comments'] = bool(data.get('enable_comments', self.DEFAULT_CONFIG['enable_comments']))
        validated['enable_download'] = bool(data.get('enable_download', self.DEFAULT_CONFIG['enable_download']))
        validated['enable_detailed_logs'] = bool(data.get('enable_detailed_logs', self.DEFAULT_CONFIG['enable_detailed_logs']))
        
        # 验证最大评论数
        max_comments = data.get('max_comments', self.DEFAULT_CONFIG['max_comments'])
        if not isinstance(max_comments, int) or max_comments <= 0:
            max_comments = self.DEFAULT_CONFIG['max_comments']
        validated['max_comments'] = int(max_comments)
        
        # 验证错误阈值
        error_threshold = data.get('error_threshold', self.DEFAULT_CONFIG['error_threshold'])
        if not isinstance(error_threshold, int) or error_threshold <= 0:
            error_threshold = self.DEFAULT_CONFIG['error_threshold']
        validated['error_threshold'] = int(error_threshold)
        
        # 验证列表类型
        validated['proxies'] = list(data.get('proxies', []))
        validated['user_agents'] = list(data.get('user_agents', []))
        
        # 验证下载路径
        download_path = data.get('download_path', self.DEFAULT_CONFIG['download_path'])
        validated['download_path'] = str(download_path)
        
        return validated
    
    def get_config(self) -> ScraperConfig:
        """获取当前配置"""
        if not self.config:
            self.config = ScraperConfig()
        return self.config
    
    def update_config(self, **kwargs) -> ScraperConfig:
        """
        更新配置
        
        Args:
            **kwargs: 要更新的配置项
            
        Returns:
            ScraperConfig: 更新后的配置
        """
        if not self.config:
            self.config = ScraperConfig()
        
        current_data = self.config.to_dict()
        current_data.update(kwargs)
        
        validated_data = self._validate_config(current_data)
        self.config = ScraperConfig(**validated_data)
        
        return self.config
    
    def generate_template(self, filepath: str = 'config_template.json') -> str:
        """
        生成配置模板文件
        
        Args:
            filepath: 模板文件路径
            
        Returns:
            str: 生成的文件路径
        """
        template = {
            "rate_limit": 1.0,
            "timeout": 30,
            "max_retries": 3,
            "output_format": "json",
            "enable_comments": False,
            "max_comments": 100,
            "proxies": [
                "http://proxy1.example.com:8080",
                "http://proxy2.example.com:8080"
            ],
            "user_agents": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            ],
            "enable_download": False,
            "download_path": "./downloads",
            "enable_detailed_logs": False,
            "error_threshold": 10
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        
        logger.info(f"配置模板已生成: {filepath}")
        return filepath


class LogManager:
    """日志管理器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.log_file = None
        self.logger = logging.getLogger('tencent_video_scraper')
    
    def setup_logging(self, log_file: Optional[str] = None, level: int = logging.INFO):
        """
        设置日志系统
        
        Args:
            log_file: 日志文件路径
            level: 日志级别
        """
        self.log_file = log_file
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        
        # 配置根日志器
        self.logger.setLevel(level)
        self.logger.addHandler(console_handler)
        
        # 文件处理器
        if log_file:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            self.logger.addHandler(file_handler)
        
        # 如果启用详细日志
        if self.config.enable_detailed_logs:
            self.logger.setLevel(logging.DEBUG)
        
        logger.info("日志系统已初始化")
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """
        记录错误信息
        
        Args:
            error: 异常对象
            context: 上下文信息
        """
        error_info = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context or {}
        }
        
        self.logger.error(f"错误: {error_info}")
        
        # 如果启用详细日志，记录堆栈跟踪
        if self.config.enable_detailed_logs:
            import traceback
            self.logger.debug(f"堆栈跟踪:\n{traceback.format_exc()}")
    
    def log_request(self, url: str, status: int, duration: float):
        """
        记录请求信息
        
        Args:
            url: 请求URL
            status: HTTP状态码
            duration: 请求耗时
        """
        if self.config.enable_detailed_logs:
            self.logger.debug(f"请求: {url}, 状态: {status}, 耗时: {duration:.2f}s")
    
    def log_progress(self, current: int, total: int, message: str = ""):
        """
        记录进度信息
        
        Args:
            current: 当前进度
            total: 总数
            message: 附加消息
        """
        progress = current / total if total > 0 else 0
        self.logger.info(f"进度: {current}/{total} ({progress:.1%}) {message}")
    
    def get_logger(self) -> logging.Logger:
        """获取日志器"""
        return self.logger