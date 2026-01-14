"""
视频解析器

从腾讯视频页面解析视频信息、播放链接和评论。
"""

import re
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .models import VideoData, VideoURL, Comment


logger = logging.getLogger(__name__)


class VideoSelectors:
    """视频页面选择器配置"""
    
    # 视频基本信息选择器
    TITLE_SELECTORS = [
        'h1.video_title',
        '.video-title h1',
        'h1[class*="title"]',
        '.player-title h1',
        'h1'
    ]
    
    DESCRIPTION_SELECTORS = [
        '.video-desc .desc-content',
        '.video-info .desc',
        '.video-description',
        '[class*="desc"] p',
        '.intro-content'
    ]
    
    DURATION_SELECTORS = [
        '.video-duration',
        '.duration',
        '[data-duration]',
        '.time-duration'
    ]
    
    VIEW_COUNT_SELECTORS = [
        '.video-view-count',
        '.play-count',
        '[class*="view"]',
        '.count-info .view'
    ]
    
    PUBLISH_TIME_SELECTORS = [
        '.video-publish-time',
        '.publish-time',
        '.upload-time',
        '[class*="time"]'
    ]
    
    THUMBNAIL_SELECTORS = [
        '.video-poster img',
        '.player-poster img',
        '.video-thumb img',
        'meta[property="og:image"]'
    ]
    
    # 视频链接选择器
    VIDEO_URL_PATTERNS = [
        r'\"url\":\"([^\"]+\.m3u8[^\"]*?)\"',
        r'\"playUrl\":\"([^\"]+)\"',
        r'src=\"([^\"]+\.mp4[^\"]*?)\"',
        r'\"video_url\":\"([^\"]+)\"',
        r'var\s+videoUrl\s*=\s*\"([^\"]+)\"',
        r'videoUrl\s*:\s*\"([^\"]+)\"',
        r'\"([^\"]*https?://[^\"]*\.(m3u8|mp4|flv)[^\"]*?)\"'
    ]
    
    # 评论选择器
    COMMENT_SELECTORS = [
        '.comment-item',
        '.comment-list .item',
        '[class*="comment"]'
    ]
    
    COMMENT_AUTHOR_SELECTORS = [
        '.comment-author',
        '.user-name',
        '.author-name'
    ]
    
    COMMENT_CONTENT_SELECTORS = [
        '.comment-content',
        '.comment-text',
        '.content'
    ]
    
    COMMENT_TIME_SELECTORS = [
        '.comment-time',
        '.publish-time',
        '.time'
    ]


class VideoParser:
    """视频解析器"""
    
    def __init__(self):
        self.selectors = VideoSelectors()
        self.stats = {
            'parsed_videos': 0,
            'parsing_errors': 0,
            'extraction_failures': {}
        }
    
    def parse_video_info(self, html: str, url: str) -> VideoData:
        """
        解析视频基本信息
        
        Args:
            html: 页面HTML内容
            url: 视频页面URL
            
        Returns:
            VideoData: 解析的视频数据
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 提取基本信息
            title = self._extract_title(soup)
            description = self._extract_description(soup)
            duration = self._extract_duration(soup, html)
            view_count = self._extract_view_count(soup, html)
            publish_time = self._extract_publish_time(soup, html)
            thumbnail_url = self._extract_thumbnail(soup, url)
            tags = self._extract_tags(soup, html)
            
            # 检测是否为SVIP内容
            is_svip = self._detect_svip_content(soup, html)
            
            # 创建视频数据对象
            video_data = VideoData(
                url=url,
                title=title,
                description=description,
                duration=duration,
                view_count=view_count,
                publish_time=publish_time,
                video_urls=[],  # 将在后续步骤中填充
                comments=[],    # 将在后续步骤中填充
                is_svip=is_svip,
                thumbnail_url=thumbnail_url,
                tags=tags
            )
            
            self.stats['parsed_videos'] += 1
            logger.info(f"成功解析视频信息: {title}")
            
            return video_data
            
        except Exception as e:
            self.stats['parsing_errors'] += 1
            logger.error(f"解析视频信息失败: {e}")
            raise
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取视频标题"""
        for selector in self.selectors.TITLE_SELECTORS:
            try:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    title = element.get_text(strip=True)
                    # 清理标题
                    title = re.sub(r'\s+', ' ', title)
                    return title
            except Exception as e:
                logger.debug(f"标题选择器 {selector} 失败: {e}")
                continue
        
        # 尝试从页面标题提取
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # 移除常见的网站后缀
            title = re.sub(r'[-_]\s*腾讯视频.*$', '', title)
            title = re.sub(r'[-_]\s*在线观看.*$', '', title)
            return title.strip()
        
        self._record_extraction_failure('title')
        return "未知标题"
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """提取视频描述"""
        for selector in self.selectors.DESCRIPTION_SELECTORS:
            try:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    desc = element.get_text(strip=True)
                    # 清理描述文本
                    desc = re.sub(r'\s+', ' ', desc)
                    return desc[:500]  # 限制长度
            except Exception as e:
                logger.debug(f"描述选择器 {selector} 失败: {e}")
                continue
        
        # 尝试从meta标签提取
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content'][:500]
        
        self._record_extraction_failure('description')
        return ""
    
    def _extract_duration(self, soup: BeautifulSoup, html: str) -> int:
        """提取视频时长（秒）"""
        # 尝试从选择器提取
        for selector in self.selectors.DURATION_SELECTORS:
            try:
                element = soup.select_one(selector)
                if element:
                    duration_text = element.get_text(strip=True)
                    duration = self._parse_duration(duration_text)
                    if duration > 0:
                        return duration
                    
                    # 尝试从data属性获取
                    data_duration = element.get('data-duration')
                    if data_duration:
                        return int(data_duration)
            except Exception as e:
                logger.debug(f"时长选择器 {selector} 失败: {e}")
                continue
        
        # 尝试从JSON数据提取
        duration_patterns = [
            r'\"duration\":(\d+)',
            r'\"videoDuration\":(\d+)',
            r'\"totalTime\":(\d+)'
        ]
        
        for pattern in duration_patterns:
            matches = re.findall(pattern, html)
            if matches:
                try:
                    return int(matches[0])
                except ValueError:
                    continue
        
        self._record_extraction_failure('duration')
        return 0
    
    def _extract_view_count(self, soup: BeautifulSoup, html: str) -> int:
        """提取播放量"""
        # 尝试从选择器提取
        for selector in self.selectors.VIEW_COUNT_SELECTORS:
            try:
                element = soup.select_one(selector)
                if element:
                    count_text = element.get_text(strip=True)
                    count = self._parse_count(count_text)
                    if count > 0:
                        return count
            except Exception as e:
                logger.debug(f"播放量选择器 {selector} 失败: {e}")
                continue
        
        # 尝试从JSON数据提取
        count_patterns = [
            r'\"playCount\":(\d+)',
            r'\"viewCount\":(\d+)',
            r'\"play_count\":(\d+)'
        ]
        
        for pattern in count_patterns:
            matches = re.findall(pattern, html)
            if matches:
                try:
                    return int(matches[0])
                except ValueError:
                    continue
        
        self._record_extraction_failure('view_count')
        return 0
    
    def _extract_publish_time(self, soup: BeautifulSoup, html: str) -> Optional[datetime]:
        """提取发布时间"""
        # 尝试从选择器提取
        for selector in self.selectors.PUBLISH_TIME_SELECTORS:
            try:
                element = soup.select_one(selector)
                if element:
                    time_text = element.get_text(strip=True)
                    parsed_time = self._parse_time(time_text)
                    if parsed_time:
                        return parsed_time
                    
                    # 尝试从datetime属性获取
                    datetime_attr = element.get('datetime')
                    if datetime_attr:
                        return self._parse_time(datetime_attr)
            except Exception as e:
                logger.debug(f"时间选择器 {selector} 失败: {e}")
                continue
        
        # 尝试从JSON数据提取
        time_patterns = [
            r'\"publishTime\":\"([^\"]+)\"',
            r'\"upload_time\":\"([^\"]+)\"',
            r'\"createTime\":\"([^\"]+)\"'
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, html)
            if matches:
                parsed_time = self._parse_time(matches[0])
                if parsed_time:
                    return parsed_time
        
        self._record_extraction_failure('publish_time')
        return None
    
    def _extract_thumbnail(self, soup: BeautifulSoup, base_url: str) -> str:
        """提取缩略图URL"""
        for selector in self.selectors.THUMBNAIL_SELECTORS:
            try:
                element = soup.select_one(selector)
                if element:
                    # 从img标签获取src
                    if element.name == 'img':
                        src = element.get('src') or element.get('data-src')
                        if src:
                            return urljoin(base_url, src)
                    
                    # 从meta标签获取content
                    elif element.name == 'meta':
                        content = element.get('content')
                        if content:
                            return urljoin(base_url, content)
            except Exception as e:
                logger.debug(f"缩略图选择器 {selector} 失败: {e}")
                continue
        
        self._record_extraction_failure('thumbnail')
        return ""
    
    def _extract_tags(self, soup: BeautifulSoup, html: str) -> List[str]:
        """提取视频标签"""
        tags = []
        
        # 从关键词meta标签提取
        keywords_meta = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_meta and keywords_meta.get('content'):
            keywords = keywords_meta['content'].split(',')
            tags.extend([tag.strip() for tag in keywords if tag.strip()])
        
        # 从标签元素提取
        tag_selectors = ['.video-tags .tag', '.tags .item', '[class*="tag"]']
        for selector in tag_selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    tag_text = element.get_text(strip=True)
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)
            except Exception as e:
                logger.debug(f"标签选择器 {selector} 失败: {e}")
                continue
        
        return tags[:10]  # 限制标签数量
    
    def _detect_svip_content(self, soup: BeautifulSoup, html: str) -> bool:
        """检测是否为SVIP专享内容"""
        # 检查SVIP相关的CSS类和文本
        svip_indicators = [
            'svip', 'vip', '会员', '专享', 'premium',
            'subscription', 'paid', '付费'
        ]
        
        # 检查页面文本
        page_text = soup.get_text().lower()
        for indicator in svip_indicators:
            if indicator in page_text:
                return True
        
        # 检查特定的SVIP元素
        svip_selectors = [
            '.svip-mark', '.vip-mark', '.premium-mark',
            '[class*="svip"]', '[class*="vip"]'
        ]
        
        for selector in svip_selectors:
            if soup.select_one(selector):
                return True
        
        # 检查JSON数据中的SVIP标识
        svip_patterns = [
            r'\"isSvip\":true',
            r'\"isVip\":true',
            r'\"isPaid\":true'
        ]
        
        for pattern in svip_patterns:
            if re.search(pattern, html):
                return True
        
        return False
    
    def _parse_duration(self, duration_text: str) -> int:
        """解析时长文本为秒数"""
        if not duration_text:
            return 0
        
        # 移除非数字字符，保留冒号
        duration_text = re.sub(r'[^\d:]', '', duration_text)
        
        # 解析 HH:MM:SS 或 MM:SS 格式
        parts = duration_text.split(':')
        if len(parts) == 3:  # HH:MM:SS
            try:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            except ValueError:
                pass
        elif len(parts) == 2:  # MM:SS
            try:
                minutes = int(parts[0])
                seconds = int(parts[1])
                return minutes * 60 + seconds
            except ValueError:
                pass
        
        # 尝试提取纯数字（假设为秒）
        numbers = re.findall(r'\d+', duration_text)
        if numbers:
            try:
                return int(numbers[0])
            except ValueError:
                pass
        
        return 0
    
    def _parse_count(self, count_text: str) -> int:
        """解析播放量文本为数字"""
        if not count_text:
            return 0
        
        # 移除非数字字符，保留小数点
        count_text = re.sub(r'[^\d.]', '', count_text)
        
        # 检查单位
        original_text = count_text.lower()
        multiplier = 1
        
        if '万' in original_text or 'w' in original_text:
            multiplier = 10000
        elif '千' in original_text or 'k' in original_text:
            multiplier = 1000
        elif '亿' in original_text:
            multiplier = 100000000
        
        try:
            number = float(count_text) if '.' in count_text else int(count_text)
            return int(number * multiplier)
        except ValueError:
            return 0
    
    def _parse_time(self, time_text: str) -> Optional[datetime]:
        """解析时间文本为datetime对象"""
        if not time_text:
            return None
        
        # 常见的时间格式
        time_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d',
            '%m-%d %H:%M',
            '%m/%d %H:%M'
        ]
        
        for fmt in time_formats:
            try:
                return datetime.strptime(time_text, fmt)
            except ValueError:
                continue
        
        # 尝试解析相对时间
        if '分钟前' in time_text:
            minutes = re.findall(r'(\d+)分钟前', time_text)
            if minutes:
                return datetime.now() - timedelta(minutes=int(minutes[0]))
        
        if '小时前' in time_text:
            hours = re.findall(r'(\d+)小时前', time_text)
            if hours:
                return datetime.now() - timedelta(hours=int(hours[0]))
        
        if '天前' in time_text:
            days = re.findall(r'(\d+)天前', time_text)
            if days:
                return datetime.now() - timedelta(days=int(days[0]))
        
        return None
    
    def _record_extraction_failure(self, field: str):
        """记录提取失败"""
        if field not in self.stats['extraction_failures']:
            self.stats['extraction_failures'][field] = 0
        self.stats['extraction_failures'][field] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取解析统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'parsed_videos': 0,
            'parsing_errors': 0,
            'extraction_failures': {}
        }


class VideoURLExtractor:
    """视频链接提取器"""
    
    def __init__(self):
        self.selectors = VideoSelectors()
        self.stats = {
            'extracted_urls': 0,
            'extraction_errors': 0
        }
    
    def extract_video_urls(self, html: str, url: str) -> List[VideoURL]:
        """
        提取视频播放链接
        
        Args:
            html: 页面HTML内容
            url: 视频页面URL
            
        Returns:
            List[VideoURL]: 提取的视频链接列表
        """
        video_urls = []
        
        try:
            # 方法1: 从HTML中使用正则提取视频链接
            for pattern in self.selectors.VIDEO_URL_PATTERNS:
                matches = re.findall(pattern, html)
                for match in matches:
                    # 处理元组结果（某些正则有多个捕获组）
                    if isinstance(match, tuple):
                        match = match[0]
                    
                    # 清理URL
                    clean_url = match.replace('\\/', '/').replace('\\', '').replace('\\u002F', '/')
                    
                    # 验证URL
                    if not self._is_valid_video_url(clean_url):
                        continue
                    
                    # 确定画质和格式
                    quality = self._determine_quality(clean_url, html)
                    format_type = self._determine_format(clean_url)
                    
                    video_url = VideoURL(
                        quality=quality,
                        url=clean_url,
                        format=format_type,
                        size=None,
                        bitrate=None
                    )
                    
                    if video_url not in video_urls:
                        video_urls.append(video_url)
            
            # 方法2: 尝试从JSON数据中提取更多信息
            self._extract_from_json_data(html, video_urls)
            
            # 方法3: 尝试从script标签中提取
            self._extract_from_script_tags(html, video_urls)
            
            # 方法4: 尝试从data属性中提取
            self._extract_from_data_attributes(html, video_urls)
            
            self.stats['extracted_urls'] += len(video_urls)
            logger.info(f"提取到 {len(video_urls)} 个视频链接")
            
        except Exception as e:
            self.stats['extraction_errors'] += 1
            logger.error(f"提取视频链接失败: {e}")
        
        return video_urls
    
    def _is_valid_video_url(self, url: str) -> bool:
        """验证是否为有效的视频URL"""
        if not url or not url.startswith('http'):
            return False
        
        # 必须包含视频格式标识
        video_indicators = ['.m3u8', '.mp4', '.flv', '.webm', '/m3u8/', '/mp4/']
        has_video_indicator = any(ind in url.lower() for ind in video_indicators)
        
        if not has_video_indicator:
            return False
        
        # 排除非视频链接
        exclude_patterns = ['poster', 'thumb', 'cover', 'image', '.jpg', '.png', '.gif', 'preview']
        url_lower = url.lower()
        for pattern in exclude_patterns:
            if pattern in url_lower:
                return False
        
        return True
    
    def _extract_from_script_tags(self, html: str, video_urls: List[VideoURL]):
        """从script标签中提取视频链接"""
        # 查找包含视频数据的script标签
        script_patterns = [
            r'<script[^>]*>.*?VIDEO_INFO\s*=\s*({.*?})\s*;?\s*</script>',
            r'<script[^>]*>.*?videoInfo\s*=\s*({.*?})\s*;?\s*</script>',
            r'<script[^>]*>.*?playinfo\s*=\s*({.*?})\s*;?\s*</script>',
        ]
        
        for pattern in script_patterns:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    data = json.loads(match)
                    self._process_json_video_data(data, video_urls)
                except json.JSONDecodeError:
                    continue
    
    def _extract_from_data_attributes(self, html: str, video_urls: List[VideoURL]):
        """从HTML data属性中提取视频链接"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 查找带有视频相关data属性的元素
        data_attrs = ['data-src', 'data-url', 'data-video', 'data-play-url']
        
        for attr in data_attrs:
            elements = soup.find_all(attrs={attr: True})
            for element in elements:
                url = element.get(attr)
                if url and self._is_valid_video_url(url):
                    video_url = VideoURL(
                        quality=self._determine_quality(url, html),
                        url=url,
                        format=self._determine_format(url),
                        size=None,
                        bitrate=None
                    )
                    if video_url not in video_urls:
                        video_urls.append(video_url)
    
    def _determine_quality(self, url: str, html: str) -> str:
        """确定视频画质"""
        url_lower = url.lower()
        
        # 从URL中判断画质
        if '1080' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        elif '360' in url_lower:
            return '360p'
        elif '240' in url_lower:
            return '240p'
        
        # 从HTML上下文中判断画质
        quality_patterns = [
            (r'\"quality\":\"([^\"]+)\".*?\"url\":\"[^\"]*' + re.escape(url), r'\1'),
            (r'\"definition\":\"([^\"]+)\".*?\"playUrl\":\"[^\"]*' + re.escape(url), r'\1')
        ]
        
        for pattern, group in quality_patterns:
            matches = re.findall(pattern, html)
            if matches:
                quality_text = matches[0].lower()
                if 'fhd' in quality_text or '1080' in quality_text:
                    return '1080p'
                elif 'hd' in quality_text or '720' in quality_text:
                    return '720p'
                elif 'sd' in quality_text or '480' in quality_text:
                    return '480p'
        
        return 'unknown'
    
    def _determine_format(self, url: str) -> str:
        """确定视频格式"""
        url_lower = url.lower()
        
        if '.m3u8' in url_lower:
            return 'm3u8'
        elif '.mp4' in url_lower:
            return 'mp4'
        elif '.flv' in url_lower:
            return 'flv'
        elif '.webm' in url_lower:
            return 'webm'
        
        return 'unknown'
    
    def _extract_from_json_data(self, html: str, video_urls: List[VideoURL]):
        """从JSON数据中提取额外信息"""
        # 查找JSON数据块
        json_patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'window\.videoInfo\s*=\s*({.+?});',
            r'var\s+videoData\s*=\s*({.+?});'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    self._process_json_video_data(data, video_urls)
                except json.JSONDecodeError:
                    continue
    
    def _process_json_video_data(self, data: dict, video_urls: List[VideoURL]):
        """处理JSON视频数据"""
        # 递归查找视频URL相关数据
        def find_video_data(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['url', 'playUrl', 'src'] and isinstance(value, str):
                        if any(ext in value.lower() for ext in ['.mp4', '.m3u8', '.flv']):
                            # 查找相关的画质和大小信息
                            quality = obj.get('quality', obj.get('definition', 'unknown'))
                            size = obj.get('size', obj.get('fileSize'))
                            bitrate = obj.get('bitrate', obj.get('bitRate'))
                            
                            video_url = VideoURL(
                                quality=str(quality),
                                url=value,
                                format=self._determine_format(value),
                                size=int(size) if size and str(size).isdigit() else None,
                                bitrate=int(bitrate) if bitrate and str(bitrate).isdigit() else None
                            )
                            
                            if video_url not in video_urls:
                                video_urls.append(video_url)
                    
                    elif isinstance(value, (dict, list)):
                        find_video_data(value, f"{path}.{key}")
            
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_video_data(item, f"{path}[{i}]")
        
        find_video_data(data)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取提取统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'extracted_urls': 0,
            'extraction_errors': 0
        }


class CommentParser:
    """评论解析器"""
    
    def __init__(self):
        self.selectors = VideoSelectors()
        self.stats = {
            'parsed_comments': 0,
            'parsing_errors': 0
        }
    
    def parse_comments(self, html: str, max_comments: int = 100) -> List[Comment]:
        """
        解析视频评论
        
        Args:
            html: 页面HTML内容
            max_comments: 最大评论数量
            
        Returns:
            List[Comment]: 解析的评论列表
        """
        comments = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 查找评论容器
            for selector in self.selectors.COMMENT_SELECTORS:
                comment_elements = soup.select(selector)
                
                for element in comment_elements[:max_comments]:
                    comment = self._parse_single_comment(element)
                    if comment:
                        comments.append(comment)
                
                if comments:
                    break  # 找到评论就停止尝试其他选择器
            
            # 如果没有找到评论，尝试从JSON数据提取
            if not comments:
                comments = self._extract_comments_from_json(html, max_comments)
            
            self.stats['parsed_comments'] += len(comments)
            logger.info(f"解析到 {len(comments)} 条评论")
            
        except Exception as e:
            self.stats['parsing_errors'] += 1
            logger.error(f"解析评论失败: {e}")
        
        return comments[:max_comments]
    
    def _parse_single_comment(self, element) -> Optional[Comment]:
        """解析单条评论"""
        try:
            # 提取作者
            author = ""
            for selector in self.selectors.COMMENT_AUTHOR_SELECTORS:
                author_element = element.select_one(selector)
                if author_element:
                    author = author_element.get_text(strip=True)
                    break
            
            # 提取内容
            content = ""
            for selector in self.selectors.COMMENT_CONTENT_SELECTORS:
                content_element = element.select_one(selector)
                if content_element:
                    content = content_element.get_text(strip=True)
                    break
            
            # 提取时间
            publish_time = None
            for selector in self.selectors.COMMENT_TIME_SELECTORS:
                time_element = element.select_one(selector)
                if time_element:
                    time_text = time_element.get_text(strip=True)
                    publish_time = self._parse_comment_time(time_text)
                    break
            
            # 验证必要字段
            if not content:
                return None
            
            # 清理和标准化文本
            content = self._clean_comment_text(content)
            author = self._clean_comment_text(author) if author else "匿名用户"
            
            return Comment(
                author=author,
                content=content,
                publish_time=publish_time,
                likes=0,  # 暂时设为0，后续可以扩展
                replies=[]  # 暂时为空，后续可以扩展
            )
            
        except Exception as e:
            logger.debug(f"解析单条评论失败: {e}")
            return None
    
    def _extract_comments_from_json(self, html: str, max_comments: int) -> List[Comment]:
        """从JSON数据中提取评论"""
        comments = []
        
        # 查找评论相关的JSON数据
        json_patterns = [
            r'window\.__COMMENT_DATA__\s*=\s*({.+?});',
            r'commentList\s*:\s*(\[.+?\])',
            r'\"comments\"\s*:\s*(\[.+?\])'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    if match.startswith('['):
                        data = json.loads(match)
                    else:
                        data = json.loads(match)
                        # 查找评论数组
                        data = self._find_comment_array(data)
                    
                    if isinstance(data, list):
                        for item in data[:max_comments]:
                            comment = self._parse_json_comment(item)
                            if comment:
                                comments.append(comment)
                    
                    if comments:
                        break
                        
                except json.JSONDecodeError:
                    continue
        
        return comments
    
    def _find_comment_array(self, data) -> list:
        """在JSON数据中查找评论数组"""
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # 查找可能包含评论的键
            comment_keys = ['comments', 'commentList', 'list', 'data', 'items']
            for key in comment_keys:
                if key in data and isinstance(data[key], list):
                    return data[key]
            
            # 递归查找
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._find_comment_array(value)
                    if result:
                        return result
        
        return []
    
    def _parse_json_comment(self, data: dict) -> Optional[Comment]:
        """解析JSON格式的评论数据"""
        try:
            # 提取字段，尝试多种可能的键名
            author_keys = ['author', 'username', 'user', 'nickname', 'name']
            content_keys = ['content', 'text', 'comment', 'message', 'body']
            time_keys = ['time', 'publishTime', 'createTime', 'timestamp', 'date']
            
            author = ""
            for key in author_keys:
                if key in data:
                    author = str(data[key])
                    break
            
            content = ""
            for key in content_keys:
                if key in data:
                    content = str(data[key])
                    break
            
            publish_time = None
            for key in time_keys:
                if key in data:
                    time_value = data[key]
                    if isinstance(time_value, (int, float)):
                        # 时间戳
                        publish_time = datetime.fromtimestamp(time_value)
                    elif isinstance(time_value, str):
                        publish_time = self._parse_comment_time(time_value)
                    break
            
            if not content:
                return None
            
            # 清理文本
            content = self._clean_comment_text(content)
            author = self._clean_comment_text(author) if author else "匿名用户"
            
            return Comment(
                author=author,
                content=content,
                publish_time=publish_time,
                likes=data.get('likes', data.get('likeCount', 0)),
                replies=[]
            )
            
        except Exception as e:
            logger.debug(f"解析JSON评论失败: {e}")
            return None
    
    def _parse_comment_time(self, time_text: str) -> Optional[datetime]:
        """解析评论时间"""
        if not time_text:
            return None
        
        # 时间格式
        time_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%m-%d %H:%M',
            '%H:%M'
        ]
        
        for fmt in time_formats:
            try:
                return datetime.strptime(time_text, fmt)
            except ValueError:
                continue
        
        # 相对时间
        relative_patterns = [
            (r'(\d+)分钟前', lambda m: datetime.now() - timedelta(minutes=int(m.group(1)))),
            (r'(\d+)小时前', lambda m: datetime.now() - timedelta(hours=int(m.group(1)))),
            (r'(\d+)天前', lambda m: datetime.now() - timedelta(days=int(m.group(1)))),
            (r'刚刚', lambda m: datetime.now()),
            (r'今天', lambda m: datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)),
            (r'昨天', lambda m: datetime.now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1))
        ]
        
        for pattern, converter in relative_patterns:
            match = re.search(pattern, time_text)
            if match:
                try:
                    return converter(match)
                except:
                    continue
        
        return None
    
    def _clean_comment_text(self, text: str) -> str:
        """清理和标准化评论文本"""
        if not text:
            return ""
        
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text.strip())
        
        # 移除特殊字符和表情符号（保留基本标点）
        text = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:()（）。，！？；：]', '', text)
        
        # 限制长度
        if len(text) > 500:
            text = text[:500] + "..."
        
        return text
    
    def get_stats(self) -> Dict[str, Any]:
        """获取解析统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'parsed_comments': 0,
            'parsing_errors': 0
        }