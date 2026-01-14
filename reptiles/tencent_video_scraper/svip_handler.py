"""
SVIP处理器

绕过腾讯视频SVIP限制，获取会员专享内容的播放链接。
"""

import re
import json
import time
import random
import logging
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import asyncio

from .http_client import HTTPClient
from .models import ScraperConfig
from .third_party_parser import ThirdPartyParserManager


logger = logging.getLogger(__name__)


class SVIPBypassStrategy:
    """SVIP绕过策略基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.success_count = 0
        self.failure_count = 0
        self.last_success_time = None
    
    async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """
        执行绕过策略
        
        Args:
            url: 视频页面URL
            html: 页面HTML内容
            http_client: HTTP客户端
            
        Returns:
            Optional[str]: 绕过后的播放链接，失败返回None
        """
        raise NotImplementedError
    
    def record_success(self):
        """记录成功"""
        self.success_count += 1
        self.last_success_time = time.time()
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class HeaderBypassStrategy(SVIPBypassStrategy):
    """请求头绕过策略 - 使用腾讯视频官方API"""
    
    def __init__(self):
        super().__init__("header_bypass")
        self.vip_headers = {
            'X-Tencent-VIP': 'true',
            'X-VIP-Level': '8',
            'X-Member-Type': 'svip',
            'X-Auth-Token': self._generate_fake_token(),
            'X-Device-ID': self._generate_device_id(),
            'X-Platform': 'web'
        }
    
    async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """使用腾讯视频官方API获取播放链接"""
        try:
            # 提取视频ID
            video_id = self._extract_video_id(url, html)
            if not video_id:
                logger.debug("无法提取视频ID")
                return None
            
            logger.info(f"尝试获取视频链接，vid: {video_id}")
            
            # 方法1: 尝试从页面JSON数据中直接提取
            video_url = self._extract_from_page_data(html)
            if video_url:
                self.record_success()
                logger.info(f"从页面数据提取成功: {video_id}")
                return video_url
            
            # 方法2: 尝试腾讯视频 getinfo API
            video_url = await self._try_getinfo_api(video_id, http_client)
            if video_url:
                self.record_success()
                logger.info(f"getinfo API成功: {video_id}")
                return video_url
            
            # 方法3: 尝试 proxyhttp API
            video_url = await self._try_proxyhttp_api(video_id, http_client)
            if video_url:
                self.record_success()
                logger.info(f"proxyhttp API成功: {video_id}")
                return video_url
            
            self.record_failure()
            return None
            
        except Exception as e:
            logger.debug(f"请求头绕过失败: {e}")
            self.record_failure()
            return None
    
    def _extract_from_page_data(self, html: str) -> Optional[str]:
        """从页面嵌入的JSON数据中提取视频链接"""
        # 查找页面中的视频数据
        patterns = [
            r'\"url\":\"(https?://[^\"]+\.m3u8[^\"]*?)\"',
            r'\"playUrl\":\"(https?://[^\"]+)\"',
            r'\"src\":\"(https?://[^\"]+\.mp4[^\"]*?)\"',
            r'\"furl\":\"(https?://[^\"]+)\"',
            r'\"vurl\":\"(https?://[^\"]+)\"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                clean_url = match.replace('\\/', '/').replace('\\u002F', '/')
                if self._is_valid_video_url(clean_url):
                    return clean_url
        
        return None
    
    def _is_valid_video_url(self, url: str) -> bool:
        """验证是否为有效的视频URL"""
        if not url or not url.startswith('http'):
            return False
        # 排除一些非视频链接
        exclude_patterns = ['poster', 'thumb', 'cover', 'image', '.jpg', '.png', '.gif']
        url_lower = url.lower()
        for pattern in exclude_patterns:
            if pattern in url_lower:
                return False
        return True
    
    async def _try_getinfo_api(self, video_id: str, http_client: HTTPClient) -> Optional[str]:
        """尝试使用 getinfo API"""
        try:
            api_url = "https://vd.l.qq.com/proxyhttp"
            
            # 构建请求体
            import json
            payload = {
                "buid": "vinfoad",
                "vinfoparam": f"vid={video_id}&charge=0&otype=json&defnpayver=1&spau=1&spaession=&sphttps=1&sphls=2&spwm=1&defn=fhd&fhdswitch=0&show1080p=1&isHLS=1&dtype=3&spsrt=1&tm={int(time.time())}&lang_code=0&logintoken=%7B%22main_login%22%3A%22%22%2C%22openid%22%3A%22%22%2C%22appid%22%3A%22%22%2C%22access_token%22%3A%22%22%2C%22vuserid%22%3A%22%22%2C%22vusession%22%3A%22%22%7D"
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Origin': 'https://v.qq.com',
                'Referer': f'https://v.qq.com/x/cover/{video_id}.html'
            }
            
            response = await http_client.post(api_url, headers=headers, json=payload)
            
            if response and hasattr(response, '_content'):
                content = response._content
                # 解析响应
                video_url = self._parse_api_response(content)
                if video_url:
                    return video_url
                    
        except Exception as e:
            logger.debug(f"getinfo API失败: {e}")
        
        return None
    
    async def _try_proxyhttp_api(self, video_id: str, http_client: HTTPClient) -> Optional[str]:
        """尝试使用 proxyhttp API"""
        try:
            api_url = f"https://vd.l.qq.com/proxyhttp"
            
            params = {
                'vid': video_id,
                'format': 'json',
                'platform': 'web',
                'defn': 'fhd',
                'fhdswitch': '0',
                'show1080p': '1'
            }
            
            headers = {
                'Origin': 'https://v.qq.com',
                'Referer': f'https://v.qq.com/x/cover/{video_id}.html'
            }
            headers.update(self.vip_headers)
            
            response = await http_client.get(api_url, params=params, headers=headers)
            
            if response and hasattr(response, '_content'):
                content = response._content
                video_url = self._parse_api_response(content)
                if video_url:
                    return video_url
                    
        except Exception as e:
            logger.debug(f"proxyhttp API失败: {e}")
        
        return None
    
    def _parse_api_response(self, content: str) -> Optional[str]:
        """解析API响应提取视频URL"""
        try:
            # 尝试解析JSON
            import json
            
            # 处理JSONP格式
            if content.startswith('QZOutputJson='):
                content = content[13:-1]  # 移除 QZOutputJson= 和末尾的 ;
            
            data = json.loads(content)
            return self._extract_video_url_from_api(data)
        except:
            # 尝试正则提取
            patterns = [
                r'\"url\":\"(https?://[^\"]+)\"',
                r'\"furl\":\"(https?://[^\"]+)\"',
                r'\"vurl\":\"(https?://[^\"]+)\"'
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    clean_url = match.replace('\\/', '/')
                    if self._is_valid_video_url(clean_url):
                        return clean_url
        return None
    
    def _extract_video_id(self, url: str, html: str) -> Optional[str]:
        """提取视频ID"""
        # 从URL中提取 - 更多模式
        url_patterns = [
            r'/x/cover/[^/]+/([a-zA-Z0-9]+)\.html',  # /x/cover/xxx/vid.html
            r'/x/cover/([a-zA-Z0-9]+)\.html',         # /x/cover/vid.html
            r'/x/page/([a-zA-Z0-9]+)\.html',          # /x/page/vid.html
            r'/x/play/([a-zA-Z0-9]+)',                # /x/play/vid
            r'vid=([a-zA-Z0-9]+)',                    # vid=xxx
            r'v=([a-zA-Z0-9]+)',                      # v=xxx
            r'/([a-zA-Z0-9]{11})\.html',              # 11位字符的vid
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, url)
            if match:
                vid = match.group(1)
                # 验证vid格式（通常是字母数字组合）
                if re.match(r'^[a-zA-Z0-9]{8,15}$', vid):
                    logger.debug(f"从URL提取到vid: {vid}")
                    return vid
        
        # 从HTML中提取 - 更多模式
        html_patterns = [
            r'\"vid\":\"([a-zA-Z0-9]+)\"',
            r'\"videoId\":\"([a-zA-Z0-9]+)\"',
            r'\"cid\":\"([a-zA-Z0-9]+)\"',
            r'vid\s*[=:]\s*[\"\'"]([a-zA-Z0-9]+)[\"\'"]',
            r'data-vid=\"([a-zA-Z0-9]+)\"',
            r'VIDEO_INFO.*?\"vid\":\"([a-zA-Z0-9]+)\"',
            r'cover_id.*?\"([a-zA-Z0-9]{11})\"',
        ]
        
        for pattern in html_patterns:
            match = re.search(pattern, html)
            if match:
                vid = match.group(1)
                if re.match(r'^[a-zA-Z0-9]{8,15}$', vid):
                    logger.debug(f"从HTML提取到vid: {vid}")
                    return vid
        
        logger.warning("无法从URL或HTML中提取视频ID")
        return None
    
    def _extract_video_url_from_api(self, data: dict) -> Optional[str]:
        """从API响应中提取视频URL"""
        try:
            # 递归查找视频URL
            def find_url(obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key in ['url', 'playUrl', 'src'] and isinstance(value, str):
                            if any(ext in value.lower() for ext in ['.m3u8', '.mp4', '.flv']):
                                return value
                        elif isinstance(value, (dict, list)):
                            result = find_url(value)
                            if result:
                                return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_url(item)
                        if result:
                            return result
                return None
            
            return find_url(data)
            
        except Exception as e:
            logger.debug(f"提取API视频URL失败: {e}")
            return None
    
    def _generate_fake_token(self) -> str:
        """生成假的认证令牌"""
        import hashlib
        timestamp = str(int(time.time()))
        random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
        token_data = f"vip_{timestamp}_{random_str}"
        return hashlib.md5(token_data.encode()).hexdigest()
    
    def _generate_device_id(self) -> str:
        """生成设备ID"""
        return ''.join(random.choices('0123456789abcdef', k=32))


class CookieBypassStrategy(SVIPBypassStrategy):
    """Cookie绕过策略"""
    
    def __init__(self):
        super().__init__("cookie_bypass")
        self.vip_cookies = {
            'vqq_vusession': self._generate_vip_session(),
            'vqq_access_token': self._generate_access_token(),
            'vqq_appid': '101483052',
            'vqq_openid': self._generate_openid(),
            'vqq_vuserid': str(random.randint(100000000, 999999999)),
            'vqq_vip': '1',
            'vqq_svip': '1'
        }
    
    async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """使用VIP Cookie绕过限制"""
        try:
            # 设置VIP Cookie
            for name, value in self.vip_cookies.items():
                http_client.session.cookie_jar.update_cookies({name: value})
            
            # 重新请求页面
            response = await http_client.get(url)
            if response.status == 200:
                new_html = await response.text()
                
                # 从新页面中提取视频链接
                video_urls = self._extract_video_urls(new_html)
                if video_urls:
                    # 选择最高画质的链接
                    best_url = self._select_best_quality(video_urls)
                    if best_url:
                        self.record_success()
                        logger.info("Cookie绕过成功")
                        return best_url
            
            self.record_failure()
            return None
            
        except Exception as e:
            logger.debug(f"Cookie绕过失败: {e}")
            self.record_failure()
            return None
    
    def _extract_video_urls(self, html: str) -> List[str]:
        """从HTML中提取视频链接"""
        patterns = [
            r'\"url\":\"([^\"]+\.m3u8[^\"]*?)\"',
            r'\"playUrl\":\"([^\"]+)\"',
            r'src=\"([^\"]+\.mp4[^\"]*?)\"'
        ]
        
        urls = []
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                clean_url = match.replace('\\/', '/').replace('\\', '')
                if clean_url not in urls:
                    urls.append(clean_url)
        
        return urls
    
    def _select_best_quality(self, urls: List[str]) -> Optional[str]:
        """选择最佳画质的视频链接"""
        if not urls:
            return None
        
        # 按画质优先级排序
        quality_priority = ['1080', 'fhd', '720', 'hd', '480', 'sd']
        
        for quality in quality_priority:
            for url in urls:
                if quality in url.lower():
                    return url
        
        # 如果没有找到特定画质，返回第一个
        return urls[0]
    
    def _generate_vip_session(self) -> str:
        """生成VIP会话ID"""
        timestamp = str(int(time.time()))
        random_part = ''.join(random.choices('0123456789abcdef', k=24))
        return f"{timestamp}{random_part}"
    
    def _generate_access_token(self) -> str:
        """生成访问令牌"""
        return ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=64))
    
    def _generate_openid(self) -> str:
        """生成OpenID"""
        return ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=32))


class TokenBypassStrategy(SVIPBypassStrategy):
    """令牌绕过策略"""
    
    def __init__(self):
        super().__init__("token_bypass")
        self.token_cache = {}
        self.token_expire_time = {}
    
    async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """使用令牌绕过限制"""
        try:
            # 获取或生成访问令牌
            token = await self._get_access_token(http_client)
            if not token:
                return None
            
            # 提取视频ID
            video_id = self._extract_video_id(url, html)
            if not video_id:
                return None
            
            # 构建带令牌的API请求
            api_url = "https://vd.l.qq.com/proxyhttp"
            params = {
                'vid': video_id,
                'access_token': token,
                'format': 'json',
                'platform': 'web_v2',
                'vip': '1'
            }
            
            response = await http_client.get(api_url, params=params)
            
            if response.status == 200:
                data = await response.json()
                video_url = self._extract_video_url(data)
                if video_url:
                    self.record_success()
                    logger.info(f"令牌绕过成功: {video_id}")
                    return video_url
            
            self.record_failure()
            return None
            
        except Exception as e:
            logger.debug(f"令牌绕过失败: {e}")
            self.record_failure()
            return None
    
    async def _get_access_token(self, http_client: HTTPClient) -> Optional[str]:
        """获取访问令牌"""
        current_time = time.time()
        
        # 检查缓存的令牌是否有效
        if 'default' in self.token_cache:
            expire_time = self.token_expire_time.get('default', 0)
            if current_time < expire_time:
                return self.token_cache['default']
        
        try:
            # 请求新的令牌
            token_url = "https://access.video.qq.com/user/auth_refresh"
            params = {
                'vappid': '11059694',
                'vsecret': 'fdf61a6be0aad57132bc5cdf78ac30145b6cd2c1470b0cfe',
                'type': 'qq',
                'g_tk': str(random.randint(1000000000, 9999999999))
            }
            
            response = await http_client.get(token_url, params=params)
            
            if response.status == 200:
                data = await response.json()
                if data.get('ret') == 0:
                    token = data.get('access_token')
                    if token:
                        # 缓存令牌（假设有效期1小时）
                        self.token_cache['default'] = token
                        self.token_expire_time['default'] = current_time + 3600
                        return token
            
            return None
            
        except Exception as e:
            logger.debug(f"获取访问令牌失败: {e}")
            return None
    
    def _extract_video_id(self, url: str, html: str) -> Optional[str]:
        """提取视频ID"""
        # 复用HeaderBypassStrategy的方法
        strategy = HeaderBypassStrategy()
        return strategy._extract_video_id(url, html)
    
    def _extract_video_url(self, data: dict) -> Optional[str]:
        """从API响应中提取视频URL"""
        # 复用HeaderBypassStrategy的方法
        strategy = HeaderBypassStrategy()
        return strategy._extract_video_url_from_api(data)


class ThirdPartyParseStrategy(SVIPBypassStrategy):
    """第三方解析接口策略 - 使用增强的第三方解析管理器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None, config_file: Optional[str] = None):
        super().__init__("third_party_parse")
        # 使用增强的第三方解析管理器
        self.parser_manager = ThirdPartyParserManager(config, config_file)
    
    async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """使用第三方解析接口获取播放链接"""
        try:
            # 使用解析管理器进行解析
            play_url = await self.parser_manager.parse(url, http_client)
            
            if play_url:
                self.record_success()
                return play_url
            
            # 如果所有第三方接口都失败，尝试直接从腾讯视频API获取预览链接
            preview_url = await self._try_preview_api(url, html, http_client)
            if preview_url:
                self.record_success()
                return preview_url
            
            self.record_failure()
            return None
            
        except Exception as e:
            logger.debug(f"第三方解析策略失败: {e}")
            self.record_failure()
            return None
    
    async def _try_preview_api(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """尝试获取预览/试看链接"""
        try:
            # 从URL或HTML中提取vid
            vid = self._extract_vid(url, html)
            if not vid:
                return None
            
            # 腾讯视频预览API
            api_url = f"https://vd.l.qq.com/proxyhttp"
            
            import json as json_module
            payload = json_module.dumps({
                "buid": "vinfoad",
                "adparam": f"vid={vid}&charge=0&otype=json"
            })
            
            headers = {
                'Content-Type': 'application/json',
                'Origin': 'https://v.qq.com',
                'Referer': f'https://v.qq.com/'
            }
            
            response = await http_client.post(api_url, headers=headers, data=payload)
            
            if response and hasattr(response, '_content'):
                content = response._content
                video_url = self._extract_url_from_text(content)
                if video_url:
                    return video_url
                    
        except Exception as e:
            logger.debug(f"预览API失败: {e}")
        
        return None
    
    def get_parser_manager(self) -> ThirdPartyParserManager:
        """获取解析管理器实例"""
        return self.parser_manager
    
    def get_strategy_count(self) -> int:
        """获取可用策略数量"""
        return self.parser_manager.get_strategy_count()
    
    def _extract_vid(self, url: str, html: str) -> Optional[str]:
        """提取视频ID"""
        patterns = [
            r'/x/cover/[^/]+/([a-zA-Z0-9]+)\.html',
            r'/x/cover/([a-zA-Z0-9]+)\.html',
            r'/x/page/([a-zA-Z0-9]+)\.html',
            r'vid=([a-zA-Z0-9]+)',
            r'\"vid\":\"([a-zA-Z0-9]+)\"',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url) or re.search(pattern, html)
            if match:
                return match.group(1)
        return None
    
    def _parse_json_response(self, content: str) -> Optional[str]:
        """解析JSON格式响应"""
        try:
            import json
            data = json.loads(content)
            
            url_keys = ['url', 'playUrl', 'video_url', 'src', 'play_url', 'vurl']
            for key in url_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, str) and self._is_valid_video_url(value):
                        return value
            
            if 'data' in data:
                nested = data['data']
                if isinstance(nested, dict):
                    for key in url_keys:
                        if key in nested and self._is_valid_video_url(str(nested[key])):
                            return nested[key]
                elif isinstance(nested, str) and self._is_valid_video_url(nested):
                    return nested
                    
        except:
            pass
        
        return self._extract_url_from_text(content)
    
    def _parse_html_response(self, content: str) -> Optional[str]:
        """解析HTML格式响应"""
        return self._extract_url_from_text(content)
    
    def _extract_url_from_text(self, content: str) -> Optional[str]:
        """从文本中提取视频URL"""
        patterns = [
            r'["\']?(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)["\']?',
            r'["\']?(https?://[^"\'<>\s]+\.mp4[^"\'<>\s]*)["\']?',
            r'url["\s:=]+["\']?(https?://[^"\'<>\s]+)["\']?',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                clean_url = match.replace('\\/', '/').replace('\\u002F', '/')
                if self._is_valid_video_url(clean_url):
                    return clean_url
        
        return None
    
    def _is_valid_video_url(self, url: str) -> bool:
        """验证是否为有效的视频URL"""
        if not url or not isinstance(url, str) or not url.startswith('http'):
            return False
        
        url_lower = url.lower()
        video_indicators = ['.m3u8', '.mp4', '.flv', '/m3u8/', '/mp4/']
        has_video = any(ind in url_lower for ind in video_indicators)
        
        exclude = ['poster', 'thumb', 'cover', '.jpg', '.png', '.gif', '.css', '.js']
        is_excluded = any(x in url_lower for x in exclude)
        
        return has_video and not is_excluded


class SVIPHandler:
    """SVIP处理器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        
        # 初始化绕过策略（第三方解析优先）
        self.bypass_strategies = [
            ThirdPartyParseStrategy(),  # 优先使用第三方解析
            HeaderBypassStrategy(),
            CookieBypassStrategy(),
            TokenBypassStrategy()
        ]
        
        # 统计信息
        self.stats = {
            'bypass_attempts': 0,
            'bypass_successes': 0,
            'svip_detections': 0,
            'strategy_usage': {}
        }
        
        # 初始化策略使用统计
        for strategy in self.bypass_strategies:
            self.stats['strategy_usage'][strategy.name] = {
                'attempts': 0,
                'successes': 0
            }
    
    async def bypass_svip_restriction(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
        """
        绕过SVIP限制获取播放链接
        
        Args:
            url: 视频页面URL
            html: 页面HTML内容
            http_client: HTTP客户端
            
        Returns:
            Optional[str]: 绕过后的播放链接，失败返回None
        """
        self.stats['bypass_attempts'] += 1
        
        # 按成功率排序策略
        sorted_strategies = sorted(
            self.bypass_strategies,
            key=lambda s: s.get_success_rate(),
            reverse=True
        )
        
        for strategy in sorted_strategies:
            try:
                logger.info(f"尝试使用策略: {strategy.name}")
                self.stats['strategy_usage'][strategy.name]['attempts'] += 1
                
                result = await strategy.bypass(url, html, http_client)
                
                if result:
                    self.stats['bypass_successes'] += 1
                    self.stats['strategy_usage'][strategy.name]['successes'] += 1
                    logger.info(f"SVIP绕过成功，使用策略: {strategy.name}")
                    return result
                
                # 策略失败，等待一段时间再尝试下一个
                await asyncio.sleep(random.uniform(1.0, 3.0))
                
            except Exception as e:
                logger.debug(f"策略 {strategy.name} 执行失败: {e}")
                continue
        
        logger.warning("所有SVIP绕过策略都失败了")
        return None
    
    def is_svip_content(self, html: str) -> bool:
        """
        检测是否为SVIP专享内容
        
        Args:
            html: 页面HTML内容
            
        Returns:
            bool: 是否为SVIP内容
        """
        # SVIP标识符
        svip_indicators = [
            'svip', 'vip', '会员', '专享', 'premium',
            'subscription', 'paid', '付费', '超级影视VIP',
            '腾讯视频VIP', '会员专享', '付费内容'
        ]
        
        # 检查页面文本
        html_lower = html.lower()
        for indicator in svip_indicators:
            if indicator in html_lower:
                self.stats['svip_detections'] += 1
                return True
        
        # 检查特定的SVIP元素和类名
        svip_patterns = [
            r'class=\"[^\"]*svip[^\"]*\"',
            r'class=\"[^\"]*vip[^\"]*\"',
            r'class=\"[^\"]*premium[^\"]*\"',
            r'data-vip=\"true\"',
            r'data-svip=\"true\"',
            r'\"isSvip\":true',
            r'\"isVip\":true',
            r'\"isPaid\":true'
        ]
        
        for pattern in svip_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                self.stats['svip_detections'] += 1
                return True
        
        # 检查URL中的SVIP标识
        svip_url_patterns = [
            r'vip=1',
            r'svip=1',
            r'paid=true',
            r'premium=true'
        ]
        
        for pattern in svip_url_patterns:
            if re.search(pattern, html):
                self.stats['svip_detections'] += 1
                return True
        
        return False
    
    def add_strategy(self, strategy: SVIPBypassStrategy):
        """添加新的绕过策略"""
        self.bypass_strategies.append(strategy)
        self.stats['strategy_usage'][strategy.name] = {
            'attempts': 0,
            'successes': 0
        }
    
    def remove_strategy(self, strategy_name: str):
        """移除绕过策略"""
        self.bypass_strategies = [
            s for s in self.bypass_strategies 
            if s.name != strategy_name
        ]
        if strategy_name in self.stats['strategy_usage']:
            del self.stats['strategy_usage'][strategy_name]
    
    def get_strategy_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取策略统计信息"""
        stats = {}
        for strategy in self.bypass_strategies:
            stats[strategy.name] = {
                'success_rate': strategy.get_success_rate(),
                'success_count': strategy.success_count,
                'failure_count': strategy.failure_count,
                'last_success_time': strategy.last_success_time,
                'attempts': self.stats['strategy_usage'][strategy.name]['attempts'],
                'successes': self.stats['strategy_usage'][strategy.name]['successes']
            }
        return stats
    
    def get_stats(self) -> Dict[str, Any]:
        """获取总体统计信息"""
        stats = self.stats.copy()
        stats['overall_success_rate'] = (
            self.stats['bypass_successes'] / self.stats['bypass_attempts']
            if self.stats['bypass_attempts'] > 0 else 0.0
        )
        stats['strategy_stats'] = self.get_strategy_stats()
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'bypass_attempts': 0,
            'bypass_successes': 0,
            'svip_detections': 0,
            'strategy_usage': {}
        }
        
        # 重置策略统计
        for strategy in self.bypass_strategies:
            strategy.success_count = 0
            strategy.failure_count = 0
            strategy.last_success_time = None
            self.stats['strategy_usage'][strategy.name] = {
                'attempts': 0,
                'successes': 0
            }


class AdvancedSVIPHandler(SVIPHandler):
    """高级SVIP处理器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        
        # 添加更多高级策略
        self.bypass_strategies.extend([
            self._create_user_agent_rotation_strategy(),
            self._create_proxy_rotation_strategy(),
            self._create_timing_attack_strategy()
        ])
    
    def _create_user_agent_rotation_strategy(self) -> SVIPBypassStrategy:
        """创建User-Agent轮换策略"""
        class UserAgentRotationStrategy(SVIPBypassStrategy):
            def __init__(self):
                super().__init__("user_agent_rotation")
                self.user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                ]
            
            async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
                # 轮换User-Agent并重新请求
                original_ua = http_client.headers.get('User-Agent')
                
                for ua in self.user_agents:
                    try:
                        http_client.headers['User-Agent'] = ua
                        response = await http_client.get(url)
                        
                        if response.status == 200:
                            new_html = await response.text()
                            # 简单的视频链接提取
                            video_urls = re.findall(r'\"url\":\"([^\"]+\.m3u8[^\"]*?)\"', new_html)
                            if video_urls:
                                self.record_success()
                                return video_urls[0].replace('\\/', '/')
                        
                        await asyncio.sleep(1)
                        
                    except Exception:
                        continue
                    finally:
                        # 恢复原始User-Agent
                        if original_ua:
                            http_client.headers['User-Agent'] = original_ua
                
                self.record_failure()
                return None
        
        return UserAgentRotationStrategy()
    
    def _create_proxy_rotation_strategy(self) -> SVIPBypassStrategy:
        """创建代理轮换策略"""
        class ProxyRotationStrategy(SVIPBypassStrategy):
            def __init__(self):
                super().__init__("proxy_rotation")
            
            async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
                # 如果有代理管理器，尝试切换代理
                if hasattr(http_client, 'proxy_manager') and http_client.proxy_manager:
                    try:
                        # 切换到下一个代理
                        http_client.proxy_manager.switch_proxy()
                        
                        # 重新请求
                        response = await http_client.get(url)
                        if response.status == 200:
                            new_html = await response.text()
                            video_urls = re.findall(r'\"url\":\"([^\"]+\.m3u8[^\"]*?)\"', new_html)
                            if video_urls:
                                self.record_success()
                                return video_urls[0].replace('\\/', '/')
                    except Exception:
                        pass
                
                self.record_failure()
                return None
        
        return ProxyRotationStrategy()
    
    def _create_timing_attack_strategy(self) -> SVIPBypassStrategy:
        """创建时序攻击策略"""
        class TimingAttackStrategy(SVIPBypassStrategy):
            def __init__(self):
                super().__init__("timing_attack")
            
            async def bypass(self, url: str, html: str, http_client: HTTPClient) -> Optional[str]:
                try:
                    # 在特定时间窗口内快速请求
                    tasks = []
                    for i in range(3):
                        task = asyncio.create_task(self._quick_request(url, http_client))
                        tasks.append(task)
                        await asyncio.sleep(0.1)  # 短暂延迟
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in results:
                        if isinstance(result, str) and result.startswith('http'):
                            self.record_success()
                            return result
                    
                    self.record_failure()
                    return None
                    
                except Exception:
                    self.record_failure()
                    return None
            
            async def _quick_request(self, url: str, http_client: HTTPClient) -> Optional[str]:
                try:
                    response = await http_client.get(url)
                    if response.status == 200:
                        html = await response.text()
                        video_urls = re.findall(r'\"url\":\"([^\"]+\.m3u8[^\"]*?)\"', html)
                        if video_urls:
                            return video_urls[0].replace('\\/', '/')
                except Exception:
                    pass
                return None
        
        return TimingAttackStrategy()