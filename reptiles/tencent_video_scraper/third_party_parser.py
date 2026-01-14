"""
第三方解析管理器

管理多个第三方视频解析接口，支持健康检查、响应时间监控、动态排序和自定义配置。
"""

import re
import json
import time
import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse
from pathlib import Path

from .http_client import HTTPClient
from .models import ScraperConfig


logger = logging.getLogger(__name__)


@dataclass
class ParserInterface:
    """解析接口数据模型"""
    name: str
    url_template: str
    response_type: str  # "json" or "html"
    enabled: bool = True
    success_count: int = 0
    failure_count: int = 0
    total_response_time: float = 0.0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    cooldown_until: Optional[float] = None  # 冷却结束时间
    consecutive_failures: int = 0
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5  # 默认50%
    
    def get_average_response_time(self) -> float:
        """获取平均响应时间"""
        if self.success_count > 0:
            return self.total_response_time / self.success_count
        return float('inf')
    
    def is_in_cooldown(self) -> bool:
        """检查是否在冷却期"""
        if self.cooldown_until is None:
            return False
        return time.time() < self.cooldown_until
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "url_template": self.url_template,
            "response_type": self.response_type,
            "enabled": self.enabled,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_response_time": self.total_response_time,
            "last_success_time": self.last_success_time,
            "last_failure_time": self.last_failure_time,
            "success_rate": self.get_success_rate(),
            "average_response_time": self.get_average_response_time()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParserInterface':
        """从字典创建实例"""
        return cls(
            name=data["name"],
            url_template=data["url_template"],
            response_type=data.get("response_type", "html"),
            enabled=data.get("enabled", True),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            total_response_time=data.get("total_response_time", 0.0),
            last_success_time=data.get("last_success_time"),
            last_failure_time=data.get("last_failure_time")
        )


class ThirdPartyParserManager:
    """第三方解析接口管理器"""
    
    # 内置的第三方解析接口列表
    DEFAULT_PARSERS = [
        {"name": "jx.777jiexi.com", "url_template": "https://jx.777jiexi.com/player/?url={url}", "response_type": "html"},
        {"name": "jx.parwix.com", "url_template": "https://jx.parwix.com:4433/player/?url={url}", "response_type": "html"},
        {"name": "www.mtosz.com", "url_template": "https://www.mtosz.com/m3u8.php?url={url}", "response_type": "json"},
        {"name": "jx.iztyy.com", "url_template": "https://jx.iztyy.com/?url={url}", "response_type": "html"},
        {"name": "jx.xmflv.com", "url_template": "https://jx.xmflv.com/?url={url}", "response_type": "html"},
        {"name": "jx.m3u8.tv", "url_template": "https://jx.m3u8.tv/jiexi/?url={url}", "response_type": "html"},
        {"name": "jx.aidouer.net", "url_template": "https://jx.aidouer.net/?url={url}", "response_type": "html"},
        {"name": "www.playm3u8.cn", "url_template": "https://www.playm3u8.cn/jiexi.php?url={url}", "response_type": "json"},
        {"name": "jx.jsonplayer.com", "url_template": "https://jx.jsonplayer.com/player/?url={url}", "response_type": "html"},
        {"name": "jx.yparse.com", "url_template": "https://jx.yparse.com/index.php?url={url}", "response_type": "html"},
    ]
    
    # 冷却时间配置（秒）
    COOLDOWN_BASE = 60  # 基础冷却时间
    COOLDOWN_MAX = 3600  # 最大冷却时间（1小时）
    MAX_CONSECUTIVE_FAILURES = 5  # 触发冷却的连续失败次数
    
    def __init__(self, config: Optional[ScraperConfig] = None, config_file: Optional[str] = None):
        """
        初始化第三方解析管理器
        
        Args:
            config: 爬虫配置
            config_file: 自定义解析接口配置文件路径
        """
        self.config = config or ScraperConfig()
        self.config_file = config_file
        self.parsers: List[ParserInterface] = []
        self.stats_file = "parser_stats.json"
        
        # 初始化解析接口
        self._init_parsers()
        
        # 加载持久化的统计数据
        self._load_stats()
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
    
    def _init_parsers(self):
        """初始化解析接口列表"""
        # 加载默认解析接口
        for parser_data in self.DEFAULT_PARSERS:
            self.parsers.append(ParserInterface(
                name=parser_data["name"],
                url_template=parser_data["url_template"],
                response_type=parser_data["response_type"]
            ))
        
        # 加载自定义配置文件
        if self.config_file:
            self._load_custom_parsers(self.config_file)
    
    def _load_custom_parsers(self, config_file: str):
        """从配置文件加载自定义解析接口"""
        try:
            path = Path(config_file)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                custom_parsers = data.get("custom_parsers", [])
                for parser_data in custom_parsers:
                    if self._validate_parser_config(parser_data):
                        # 检查是否已存在
                        existing = self.get_parser_by_name(parser_data["name"])
                        if existing:
                            # 更新现有配置
                            existing.url_template = parser_data["url_template"]
                            existing.response_type = parser_data.get("response_type", "html")
                            existing.enabled = parser_data.get("enabled", True)
                        else:
                            # 添加新接口
                            self.parsers.append(ParserInterface(
                                name=parser_data["name"],
                                url_template=parser_data["url_template"],
                                response_type=parser_data.get("response_type", "html"),
                                enabled=parser_data.get("enabled", True)
                            ))
                
                logger.info(f"已加载 {len(custom_parsers)} 个自定义解析接口")
        except Exception as e:
            logger.error(f"加载自定义解析接口配置失败: {e}")
    
    def _validate_parser_config(self, parser_data: Dict[str, Any]) -> bool:
        """验证解析接口配置格式"""
        required_fields = ["name", "url_template"]
        for field in required_fields:
            if field not in parser_data:
                logger.warning(f"解析接口配置缺少必需字段: {field}")
                return False
        
        # 验证URL模板格式
        url_template = parser_data["url_template"]
        if "{url}" not in url_template:
            logger.warning(f"URL模板必须包含 {{url}} 占位符: {url_template}")
            return False
        
        # 验证响应类型
        response_type = parser_data.get("response_type", "html")
        if response_type not in ["json", "html"]:
            logger.warning(f"无效的响应类型: {response_type}")
            return False
        
        return True
    
    def _load_stats(self):
        """加载持久化的统计数据"""
        try:
            path = Path(self.stats_file)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    stats_data = json.load(f)
                
                for parser in self.parsers:
                    if parser.name in stats_data:
                        stats = stats_data[parser.name]
                        parser.success_count = stats.get("success_count", 0)
                        parser.failure_count = stats.get("failure_count", 0)
                        parser.total_response_time = stats.get("total_response_time", 0.0)
                        parser.last_success_time = stats.get("last_success_time")
                        parser.last_failure_time = stats.get("last_failure_time")
                
                logger.debug("已加载解析接口统计数据")
        except Exception as e:
            logger.debug(f"加载统计数据失败: {e}")
    
    def save_stats(self):
        """保存统计数据到文件"""
        try:
            stats_data = {}
            for parser in self.parsers:
                stats_data[parser.name] = {
                    "success_count": parser.success_count,
                    "failure_count": parser.failure_count,
                    "total_response_time": parser.total_response_time,
                    "last_success_time": parser.last_success_time,
                    "last_failure_time": parser.last_failure_time
                }
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, ensure_ascii=False, indent=2)
            
            logger.debug("已保存解析接口统计数据")
        except Exception as e:
            logger.error(f"保存统计数据失败: {e}")

    
    def get_sorted_parsers(self) -> List[ParserInterface]:
        """
        按成功率和响应时间动态排序返回解析接口列表
        
        排序规则：
        1. 排除禁用和冷却中的接口
        2. 按成功率降序排序
        3. 成功率相同时按平均响应时间升序排序
        """
        available_parsers = [
            p for p in self.parsers 
            if p.enabled and not p.is_in_cooldown()
        ]
        
        return sorted(
            available_parsers,
            key=lambda p: (-p.get_success_rate(), p.get_average_response_time())
        )
    
    def get_parser_by_name(self, name: str) -> Optional[ParserInterface]:
        """根据名称获取解析接口"""
        for parser in self.parsers:
            if parser.name == name:
                return parser
        return None
    
    def add_parser(self, name: str, url_template: str, response_type: str = "html") -> bool:
        """
        添加自定义解析接口
        
        Args:
            name: 接口名称
            url_template: URL模板，必须包含{url}占位符
            response_type: 响应类型，"json"或"html"
            
        Returns:
            bool: 是否添加成功
        """
        # 验证配置
        config = {"name": name, "url_template": url_template, "response_type": response_type}
        if not self._validate_parser_config(config):
            return False
        
        # 检查是否已存在
        if self.get_parser_by_name(name):
            logger.warning(f"解析接口已存在: {name}")
            return False
        
        # 添加新接口
        self.parsers.append(ParserInterface(
            name=name,
            url_template=url_template,
            response_type=response_type
        ))
        
        logger.info(f"已添加解析接口: {name}")
        return True
    
    def remove_parser(self, name: str) -> bool:
        """
        移除解析接口
        
        Args:
            name: 接口名称
            
        Returns:
            bool: 是否移除成功
        """
        parser = self.get_parser_by_name(name)
        if parser:
            self.parsers.remove(parser)
            logger.info(f"已移除解析接口: {name}")
            return True
        
        logger.warning(f"解析接口不存在: {name}")
        return False
    
    def enable_parser(self, name: str) -> bool:
        """启用解析接口"""
        parser = self.get_parser_by_name(name)
        if parser:
            parser.enabled = True
            logger.info(f"已启用解析接口: {name}")
            return True
        return False
    
    def disable_parser(self, name: str) -> bool:
        """禁用解析接口"""
        parser = self.get_parser_by_name(name)
        if parser:
            parser.enabled = False
            logger.info(f"已禁用解析接口: {name}")
            return True
        return False
    
    def _record_success(self, parser: ParserInterface, response_time: float):
        """记录成功"""
        parser.success_count += 1
        parser.total_response_time += response_time
        parser.last_success_time = time.time()
        parser.consecutive_failures = 0
        parser.cooldown_until = None
    
    def _record_failure(self, parser: ParserInterface):
        """记录失败并处理冷却"""
        parser.failure_count += 1
        parser.last_failure_time = time.time()
        parser.consecutive_failures += 1
        
        # 连续失败达到阈值，进入冷却期
        if parser.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            cooldown_time = min(
                self.COOLDOWN_BASE * (2 ** (parser.consecutive_failures - self.MAX_CONSECUTIVE_FAILURES)),
                self.COOLDOWN_MAX
            )
            parser.cooldown_until = time.time() + cooldown_time
            logger.warning(f"解析接口 {parser.name} 进入冷却期 {cooldown_time} 秒")
    
    async def parse(self, video_url: str, http_client: HTTPClient) -> Optional[str]:
        """
        使用第三方接口解析视频链接
        
        Args:
            video_url: 腾讯视频URL
            http_client: HTTP客户端
            
        Returns:
            Optional[str]: 解析后的播放链接，失败返回None
        """
        # 清理URL
        parsed = urlparse(video_url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        encoded_url = quote(clean_url, safe='')
        
        # 获取排序后的解析接口
        sorted_parsers = self.get_sorted_parsers()
        
        if not sorted_parsers:
            logger.error("没有可用的解析接口")
            return None
        
        for parser in sorted_parsers:
            try:
                # 构建请求URL
                api_url = parser.url_template.format(url=encoded_url)
                
                logger.info(f"尝试第三方解析: {parser.name}")
                
                # 发送请求并计时
                start_time = time.time()
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate',
                }
                
                response = await http_client.get(api_url, headers=headers)
                response_time = time.time() - start_time
                
                if response and hasattr(response, '_content'):
                    content = response._content
                    
                    # 根据响应类型解析
                    if parser.response_type == "json":
                        play_url = self._parse_json_response(content)
                    else:
                        play_url = self._parse_html_response(content)
                    
                    # 验证链接有效性
                    if play_url and self.validate_play_url(play_url):
                        self._record_success(parser, response_time)
                        logger.info(f"第三方解析成功: {parser.name}, 耗时: {response_time:.2f}s")
                        return play_url
                
                # 解析失败
                self._record_failure(parser)
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.debug(f"第三方解析 {parser.name} 失败: {e}")
                self._record_failure(parser)
                continue
        
        logger.warning("所有第三方解析接口都失败了")
        return None
    
    def _parse_json_response(self, content: str) -> Optional[str]:
        """解析JSON格式响应"""
        try:
            data = json.loads(content)
            
            # 常见的URL字段名
            url_keys = ['url', 'playUrl', 'video_url', 'src', 'play_url', 'vurl', 'data']
            
            for key in url_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, str) and self._is_video_url(value):
                        return value
                    elif isinstance(value, dict):
                        # 递归查找
                        for sub_key in url_keys:
                            if sub_key in value and self._is_video_url(str(value[sub_key])):
                                return value[sub_key]
            
            # 递归搜索
            return self._find_url_in_dict(data)
            
        except json.JSONDecodeError:
            pass
        
        # 尝试从文本中提取
        return self._extract_url_from_text(content)
    
    def _parse_html_response(self, content: str) -> Optional[str]:
        """解析HTML格式响应"""
        return self._extract_url_from_text(content)
    
    def _find_url_in_dict(self, obj: Any, depth: int = 0) -> Optional[str]:
        """递归在字典中查找视频URL"""
        if depth > 5:  # 限制递归深度
            return None
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and self._is_video_url(value):
                    return value
                elif isinstance(value, (dict, list)):
                    result = self._find_url_in_dict(value, depth + 1)
                    if result:
                        return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_url_in_dict(item, depth + 1)
                if result:
                    return result
        
        return None
    
    def _extract_url_from_text(self, content: str) -> Optional[str]:
        """从文本中提取视频URL"""
        patterns = [
            r'["\']?(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)["\']?',
            r'["\']?(https?://[^"\'<>\s]+\.mp4[^"\'<>\s]*)["\']?',
            r'["\']?(https?://[^"\'<>\s]+\.flv[^"\'<>\s]*)["\']?',
            r'url["\s:=]+["\']?(https?://[^"\'<>\s]+)["\']?',
            r'source["\s:=]+["\']?(https?://[^"\'<>\s]+)["\']?',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                clean_url = match.replace('\\/', '/').replace('\\u002F', '/')
                if self._is_video_url(clean_url):
                    return clean_url
        
        return None
    
    def _is_video_url(self, url: str) -> bool:
        """检查是否为视频URL"""
        if not url or not isinstance(url, str) or not url.startswith('http'):
            return False
        
        url_lower = url.lower()
        
        # 视频格式标识
        video_indicators = ['.m3u8', '.mp4', '.flv', '/m3u8/', '/mp4/', '/flv/']
        has_video = any(ind in url_lower for ind in video_indicators)
        
        # 排除非视频链接
        exclude = ['poster', 'thumb', 'cover', '.jpg', '.png', '.gif', '.css', '.js', 'favicon']
        is_excluded = any(x in url_lower for x in exclude)
        
        return has_video and not is_excluded
    
    def validate_play_url(self, url: str) -> bool:
        """
        验证播放链接的格式有效性
        
        Args:
            url: 播放链接
            
        Returns:
            bool: 是否有效
        """
        if not url or not isinstance(url, str):
            return False
        
        # 检查URL格式
        if not url.startswith(('http://', 'https://')):
            return False
        
        # 检查是否包含视频格式标识
        url_lower = url.lower()
        valid_extensions = ['.m3u8', '.mp4', '.flv', '.ts']
        valid_protocols = ['/m3u8/', '/mp4/', '/flv/', '/hls/', '/dash/']
        
        has_valid_format = (
            any(ext in url_lower for ext in valid_extensions) or
            any(proto in url_lower for proto in valid_protocols)
        )
        
        if not has_valid_format:
            return False
        
        # 检查URL长度（过短或过长都可能无效）
        if len(url) < 20 or len(url) > 2000:
            return False
        
        # 检查是否包含明显的无效字符
        invalid_chars = ['<', '>', '"', "'", '\n', '\r', '\t']
        if any(char in url for char in invalid_chars):
            return False
        
        return True
    
    async def check_url_accessible(self, url: str, http_client: HTTPClient) -> bool:
        """
        检测链接是否可访问
        
        Args:
            url: 播放链接
            http_client: HTTP客户端
            
        Returns:
            bool: 是否可访问
        """
        try:
            # 发送HEAD请求检查
            session = await http_client._get_session()
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                return response.status in [200, 206, 302, 301]
        except Exception:
            return False

    
    async def health_check(self, http_client: HTTPClient) -> Dict[str, bool]:
        """
        对所有解析接口进行健康检查
        
        Args:
            http_client: HTTP客户端
            
        Returns:
            Dict[str, bool]: 接口名称到健康状态的映射
        """
        results = {}
        test_url = "https://v.qq.com/x/cover/test.html"
        
        for parser in self.parsers:
            try:
                api_url = parser.url_template.format(url=quote(test_url, safe=''))
                
                start_time = time.time()
                response = await http_client.get(api_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                response_time = time.time() - start_time
                
                # 检查响应是否正常（即使没有解析结果，只要能响应就算健康）
                is_healthy = response is not None and response_time < 30
                results[parser.name] = is_healthy
                
                if is_healthy:
                    logger.debug(f"解析接口 {parser.name} 健康检查通过，响应时间: {response_time:.2f}s")
                else:
                    logger.warning(f"解析接口 {parser.name} 健康检查失败")
                    
            except Exception as e:
                results[parser.name] = False
                logger.warning(f"解析接口 {parser.name} 健康检查异常: {e}")
        
        return results
    
    async def start_health_check(self, http_client: HTTPClient, interval: int = 300):
        """
        启动定期健康检查
        
        Args:
            http_client: HTTP客户端
            interval: 检查间隔（秒）
        """
        self._running = True
        
        async def _check_loop():
            while self._running:
                try:
                    await self.health_check(http_client)
                    self.save_stats()
                except Exception as e:
                    logger.error(f"健康检查循环异常: {e}")
                
                await asyncio.sleep(interval)
        
        self._health_check_task = asyncio.create_task(_check_loop())
        logger.info(f"已启动解析接口健康检查，间隔: {interval}秒")
    
    async def stop_health_check(self):
        """停止健康检查"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("已停止解析接口健康检查")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取所有解析接口的统计信息"""
        return {
            "total_parsers": len(self.parsers),
            "enabled_parsers": len([p for p in self.parsers if p.enabled]),
            "available_parsers": len(self.get_sorted_parsers()),
            "parsers": [p.to_dict() for p in self.parsers]
        }
    
    def get_parser_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定解析接口的统计信息"""
        parser = self.get_parser_by_name(name)
        if parser:
            return parser.to_dict()
        return None
    
    def reset_stats(self):
        """重置所有统计数据"""
        for parser in self.parsers:
            parser.success_count = 0
            parser.failure_count = 0
            parser.total_response_time = 0.0
            parser.last_success_time = None
            parser.last_failure_time = None
            parser.consecutive_failures = 0
            parser.cooldown_until = None
        
        logger.info("已重置所有解析接口统计数据")
    
    def save_custom_config(self, config_file: str):
        """
        保存自定义解析接口配置到文件
        
        Args:
            config_file: 配置文件路径
        """
        try:
            # 只保存非默认的解析接口
            default_names = {p["name"] for p in self.DEFAULT_PARSERS}
            custom_parsers = [
                {
                    "name": p.name,
                    "url_template": p.url_template,
                    "response_type": p.response_type,
                    "enabled": p.enabled
                }
                for p in self.parsers
                if p.name not in default_names
            ]
            
            config_data = {"custom_parsers": custom_parsers}
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存自定义解析接口配置到: {config_file}")
            
        except Exception as e:
            logger.error(f"保存自定义配置失败: {e}")
    
    def get_strategy_count(self) -> int:
        """获取可用策略数量（用于Property 23验证）"""
        return len([p for p in self.parsers if p.enabled])
