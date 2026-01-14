"""
视频解析器属性测试

测试视频信息完整性和多策略解析适应性。
Feature: tencent-video-scraper, Property 1: 视频信息完整性
Feature: tencent-video-scraper, Property 15: 多策略解析适应性
"""

import pytest
from hypothesis import given, strategies as st, settings
from bs4 import BeautifulSoup
from datetime import datetime
import json

from tencent_video_scraper.parser import VideoParser, VideoURLExtractor, CommentParser
from tencent_video_scraper.models import VideoData, VideoURL, Comment


class TestVideoInformationIntegrity:
    """测试视频信息完整性"""
    
    @given(
        title=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        description=st.text(min_size=0, max_size=500),
        duration_seconds=st.integers(min_value=1, max_value=7200),
        view_count=st.integers(min_value=0, max_value=1000000000),
        publish_year=st.integers(min_value=2010, max_value=2024),
        publish_month=st.integers(min_value=1, max_value=12),
        publish_day=st.integers(min_value=1, max_value=28)
    )
    @settings(max_examples=50, deadline=5000)
    def test_video_information_completeness(self, title, description, duration_seconds, 
                                          view_count, publish_year, publish_month, publish_day):
        """
        测试视频信息完整性 - 解析器应该提取出包含所有必要字段的完整视频信息
        Feature: tencent-video-scraper, Property 1: 视频信息完整性
        """
        # 生成测试HTML
        html = self._generate_video_html(
            title, description, duration_seconds, view_count,
            publish_year, publish_month, publish_day
        )
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/x/cover/test.html")
        
        # 验证必要字段存在且格式正确
        assert video_data.title, "标题不能为空"
        assert isinstance(video_data.title, str), "标题必须是字符串"
        assert len(video_data.title.strip()) > 0, "标题不能只包含空白字符"
        
        assert isinstance(video_data.description, str), "描述必须是字符串"
        
        assert isinstance(video_data.duration, int), "时长必须是整数"
        assert video_data.duration >= 0, "时长不能为负数"
        
        assert isinstance(video_data.view_count, int), "播放量必须是整数"
        assert video_data.view_count >= 0, "播放量不能为负数"
        
        if video_data.publish_time:
            assert isinstance(video_data.publish_time, datetime), "发布时间必须是datetime对象"
        
        assert isinstance(video_data.url, str), "URL必须是字符串"
        assert video_data.url.startswith('http'), "URL必须是有效的HTTP链接"
        
        assert isinstance(video_data.is_svip, bool), "SVIP标识必须是布尔值"
        
        assert isinstance(video_data.thumbnail_url, str), "缩略图URL必须是字符串"
        
        assert isinstance(video_data.tags, list), "标签必须是列表"
        assert all(isinstance(tag, str) for tag in video_data.tags), "所有标签必须是字符串"
        
        assert isinstance(video_data.video_urls, list), "视频链接列表必须是列表"
        assert isinstance(video_data.comments, list), "评论列表必须是列表"
    
    @given(
        title_variations=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=3),
        selector_count=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=30, deadline=5000)
    def test_title_extraction_robustness(self, title_variations, selector_count):
        """
        测试标题提取的鲁棒性 - 应该能从多种HTML结构中提取标题
        Feature: tencent-video-scraper, Property 1: 视频信息完整性
        """
        # 生成包含多种标题选择器的HTML
        html_parts = ["<html><head><title>页面标题</title></head><body>"]
        
        for i, title in enumerate(title_variations[:selector_count]):
            if i == 0:
                html_parts.append(f'<h1 class="video_title">{title}</h1>')
            elif i == 1:
                html_parts.append(f'<div class="video-title"><h1>{title}</h1></div>')
            elif i == 2:
                html_parts.append(f'<h1 class="player-title">{title}</h1>')
        
        html_parts.append("</body></html>")
        html = "".join(html_parts)
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/test")
        
        # 应该提取到第一个有效的标题
        assert video_data.title in title_variations, f"提取的标题 '{video_data.title}' 应该在预期列表中"
        assert len(video_data.title.strip()) > 0, "提取的标题不能为空"
    
    @given(
        duration_format=st.sampled_from(['seconds', 'mm:ss', 'hh:mm:ss', 'text']),
        duration_value=st.integers(min_value=30, max_value=7200)
    )
    @settings(max_examples=40, deadline=5000)
    def test_duration_parsing_formats(self, duration_format, duration_value):
        """
        测试时长解析的多种格式支持
        Feature: tencent-video-scraper, Property 1: 视频信息完整性
        """
        # 根据格式生成时长文本
        if duration_format == 'seconds':
            duration_text = str(duration_value)
        elif duration_format == 'mm:ss':
            minutes = duration_value // 60
            seconds = duration_value % 60
            duration_text = f"{minutes:02d}:{seconds:02d}"
        elif duration_format == 'hh:mm:ss':
            hours = duration_value // 3600
            minutes = (duration_value % 3600) // 60
            seconds = duration_value % 60
            duration_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:  # text format
            minutes = duration_value // 60
            seconds = duration_value % 60
            duration_text = f"{minutes}分{seconds}秒"
        
        html = f"""
        <html>
        <body>
            <h1>测试视频</h1>
            <div class="video-duration">{duration_text}</div>
        </body>
        </html>
        """
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/test")
        
        # 验证时长解析正确（允许小的误差）
        assert abs(video_data.duration - duration_value) <= 1, \
            f"解析的时长 {video_data.duration} 与预期 {duration_value} 相差过大"
    
    @given(
        view_count_format=st.sampled_from(['number', 'k', 'w', 'mixed']),
        base_count=st.integers(min_value=100, max_value=999999)
    )
    @settings(max_examples=40, deadline=5000)
    def test_view_count_parsing_formats(self, view_count_format, base_count):
        """
        测试播放量解析的多种格式支持
        Feature: tencent-video-scraper, Property 1: 视频信息完整性
        """
        # 根据格式生成播放量文本
        if view_count_format == 'number':
            count_text = str(base_count)
            expected_count = base_count
        elif view_count_format == 'k':
            count_text = f"{base_count / 1000:.1f}k"
            expected_count = int(base_count / 1000 * 1000)
        elif view_count_format == 'w':
            count_text = f"{base_count / 10000:.1f}万"
            expected_count = int(base_count / 10000 * 10000)
        else:  # mixed
            if base_count > 10000:
                count_text = f"{base_count / 10000:.1f}万次播放"
                expected_count = int(base_count / 10000 * 10000)
            else:
                count_text = f"{base_count}次播放"
                expected_count = base_count
        
        html = f"""
        <html>
        <body>
            <h1>测试视频</h1>
            <div class="video-view-count">{count_text}</div>
        </body>
        </html>
        """
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/test")
        
        # 验证播放量解析正确（允许一定误差）
        relative_error = abs(video_data.view_count - expected_count) / max(expected_count, 1)
        assert relative_error <= 0.1, \
            f"解析的播放量 {video_data.view_count} 与预期 {expected_count} 相差过大"
    
    def _generate_video_html(self, title, description, duration_seconds, view_count,
                           publish_year, publish_month, publish_day):
        """生成测试用的视频HTML"""
        # 格式化时长
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        
        # 格式化播放量
        if view_count > 10000:
            view_str = f"{view_count / 10000:.1f}万"
        else:
            view_str = str(view_count)
        
        # 格式化日期
        publish_date = f"{publish_year}-{publish_month:02d}-{publish_day:02d}"
        
        return f"""
        <html>
        <head>
            <title>{title} - 腾讯视频</title>
            <meta name="description" content="{description}">
            <meta name="keywords" content="视频,娱乐,腾讯">
        </head>
        <body>
            <h1 class="video_title">{title}</h1>
            <div class="video-desc">
                <div class="desc-content">{description}</div>
            </div>
            <div class="video-duration">{duration_str}</div>
            <div class="video-view-count">{view_str}</div>
            <div class="video-publish-time">{publish_date}</div>
            <div class="video-poster">
                <img src="https://example.com/thumb.jpg" alt="缩略图">
            </div>
            <div class="video-tags">
                <span class="tag">标签1</span>
                <span class="tag">标签2</span>
            </div>
        </body>
        </html>
        """


class TestMultiStrategyParsingAdaptability:
    """测试多策略解析适应性"""
    
    @given(
        strategy_count=st.integers(min_value=2, max_value=4),
        working_strategy_index=st.integers(min_value=0, max_value=3),
        title=st.text(min_size=5, max_size=50).filter(lambda x: x.strip())
    )
    @settings(max_examples=30, deadline=5000)
    def test_fallback_parsing_strategies(self, strategy_count, working_strategy_index, title):
        """
        测试解析器的回退策略 - 当某些选择器失败时应该尝试其他策略
        Feature: tencent-video-scraper, Property 15: 多策略解析适应性
        """
        # 确保工作策略索引在范围内
        working_strategy_index = working_strategy_index % strategy_count
        
        # 生成包含多种策略的HTML，只有一种策略有效
        html_parts = ["<html><body>"]
        
        for i in range(strategy_count):
            if i == working_strategy_index:
                # 这个策略包含有效数据
                html_parts.append(f'<h1 class="strategy-{i}">{title}</h1>')
            else:
                # 这个策略包含无效或空数据
                html_parts.append(f'<h1 class="strategy-{i}"></h1>')
        
        html_parts.append("</body></html>")
        html = "".join(html_parts)
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/test")
        
        # 应该成功提取到标题，即使前面的策略失败了
        assert video_data.title == title, f"应该提取到标题 '{title}'，实际得到 '{video_data.title}'"
    
    @given(
        broken_html_type=st.sampled_from(['missing_tags', 'malformed_tags', 'empty_content', 'special_chars']),
        title=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    @settings(max_examples=40, deadline=5000)
    def test_broken_html_handling(self, broken_html_type, title):
        """
        测试对损坏HTML的处理能力
        Feature: tencent-video-scraper, Property 15: 多策略解析适应性
        """
        # 根据类型生成不同的损坏HTML
        if broken_html_type == 'missing_tags':
            html = f"<html><body><h1 class='video_title'>{title}<div>其他内容</div></body></html>"
        elif broken_html_type == 'malformed_tags':
            html = f"<html><body><h1 class='video_title'>{title}</h2><p>内容</body></html>"
        elif broken_html_type == 'empty_content':
            html = f"<html><body><h1 class='video_title'></h1><title>{title}</title></body></html>"
        else:  # special_chars
            escaped_title = title.replace('<', '&lt;').replace('>', '&gt;')
            html = f"<html><body><h1 class='video_title'>{escaped_title}</h1></body></html>"
        
        parser = VideoParser()
        
        # 解析不应该崩溃
        try:
            video_data = parser.parse_video_info(html, "https://v.qq.com/test")
            
            # 应该至少提取到一些基本信息
            assert isinstance(video_data.title, str), "标题应该是字符串"
            assert len(video_data.title) > 0, "应该提取到非空标题"
            
        except Exception as e:
            pytest.fail(f"解析损坏的HTML时不应该抛出异常: {e}")
    
    @given(
        encoding_type=st.sampled_from(['utf-8', 'gbk', 'mixed']),
        title=st.text(min_size=1, max_size=30).filter(lambda x: x.strip() and all(ord(c) < 65536 for c in x))
    )
    @settings(max_examples=30, deadline=5000)
    def test_encoding_handling(self, encoding_type, title):
        """
        测试不同编码的处理能力
        Feature: tencent-video-scraper, Property 15: 多策略解析适应性
        """
        # 生成包含中文字符的HTML
        chinese_title = f"{title}中文测试"
        
        if encoding_type == 'utf-8':
            html = f"""
            <html>
            <head><meta charset="utf-8"></head>
            <body><h1 class="video_title">{chinese_title}</h1></body>
            </html>
            """
        elif encoding_type == 'gbk':
            html = f"""
            <html>
            <head><meta charset="gbk"></head>
            <body><h1 class="video_title">{chinese_title}</h1></body>
            </html>
            """
        else:  # mixed
            html = f"""
            <html>
            <body><h1 class="video_title">{chinese_title}</h1></body>
            </html>
            """
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/test")
        
        # 应该正确处理中文字符
        assert chinese_title in video_data.title or title in video_data.title, \
            f"标题应该包含原始文本，实际得到: '{video_data.title}'"
    
    @given(
        json_structure=st.sampled_from(['nested', 'array', 'mixed']),
        title=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        duration=st.integers(min_value=60, max_value=3600)
    )
    @settings(max_examples=30, deadline=5000)
    def test_json_data_extraction(self, json_structure, title, duration):
        """
        测试从JSON数据中提取信息的能力
        Feature: tencent-video-scraper, Property 15: 多策略解析适应性
        """
        # 根据结构类型生成不同的JSON数据
        if json_structure == 'nested':
            json_data = {
                "videoInfo": {
                    "title": title,
                    "duration": duration,
                    "playCount": 12345
                }
            }
        elif json_structure == 'array':
            json_data = [
                {"type": "video", "title": title, "duration": duration},
                {"type": "other", "title": "其他"}
            ]
        else:  # mixed
            json_data = {
                "data": {
                    "list": [
                        {"videoTitle": title, "videoDuration": duration}
                    ]
                }
            }
        
        # 生成包含JSON数据的HTML
        json_str = json.dumps(json_data, ensure_ascii=False)
        html = f"""
        <html>
        <body>
            <h1>页面标题</h1>
            <script>
                window.videoData = {json_str};
            </script>
        </body>
        </html>
        """
        
        parser = VideoParser()
        video_data = parser.parse_video_info(html, "https://v.qq.com/test")
        
        # 应该能够从HTML标签或JSON数据中提取信息
        assert isinstance(video_data.title, str), "应该提取到标题"
        assert len(video_data.title) > 0, "标题不能为空"
        assert isinstance(video_data.duration, int), "时长应该是整数"


class TestVideoURLExtraction:
    """测试视频链接提取"""
    
    @given(
        url_format=st.sampled_from(['m3u8', 'mp4', 'mixed']),
        quality=st.sampled_from(['1080p', '720p', '480p']),
        url_count=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=30, deadline=5000)
    def test_video_url_extraction_capability(self, url_format, quality, url_count):
        """
        测试视频链接获取能力
        Feature: tencent-video-scraper, Property 2: 视频链接获取能力
        """
        # 生成测试URL
        base_urls = []
        for i in range(url_count):
            if url_format == 'm3u8':
                url = f"https://example.com/video_{i}_{quality}.m3u8"
            elif url_format == 'mp4':
                url = f"https://example.com/video_{i}_{quality}.mp4"
            else:  # mixed
                ext = 'm3u8' if i % 2 == 0 else 'mp4'
                url = f"https://example.com/video_{i}_{quality}.{ext}"
            base_urls.append(url)
        
        # 生成包含视频链接的HTML
        html_parts = ["<html><body>"]
        for url in base_urls:
            html_parts.append(f'<script>var videoUrl = "{url}";</script>')
        html_parts.append("</body></html>")
        html = "".join(html_parts)
        
        extractor = VideoURLExtractor()
        video_urls = extractor.extract_video_urls(html, "https://v.qq.com/test")
        
        # 应该提取到至少一个视频链接
        assert len(video_urls) > 0, "应该提取到至少一个视频链接"
        
        # 验证提取的链接格式正确
        for video_url in video_urls:
            assert isinstance(video_url.url, str), "视频URL应该是字符串"
            assert video_url.url.startswith('http'), "视频URL应该是有效的HTTP链接"
            assert isinstance(video_url.quality, str), "画质应该是字符串"
            assert isinstance(video_url.format, str), "格式应该是字符串"
    
    @given(
        quality_indicators=st.lists(
            st.sampled_from(['1080', '720', '480', 'fhd', 'hd', 'sd']),
            min_size=1, max_size=3
        )
    )
    @settings(max_examples=30, deadline=5000)
    def test_quality_detection_accuracy(self, quality_indicators):
        """
        测试画质检测的准确性
        Feature: tencent-video-scraper, Property 2: 视频链接获取能力
        """
        html_parts = ["<html><body>"]
        
        for indicator in quality_indicators:
            url = f"https://example.com/video_{indicator}.m3u8"
            html_parts.append(f'<script>var url = "{url}";</script>')
        
        html_parts.append("</body></html>")
        html = "".join(html_parts)
        
        extractor = VideoURLExtractor()
        video_urls = extractor.extract_video_urls(html, "https://v.qq.com/test")
        
        # 验证画质检测
        for video_url in video_urls:
            quality_lower = video_url.quality.lower()
            
            # 检查画质是否合理
            valid_qualities = ['1080p', '720p', '480p', '360p', '240p', 'unknown']
            assert quality_lower in [q.lower() for q in valid_qualities], \
                f"检测到的画质 '{video_url.quality}' 不在有效范围内"


class TestCommentParsing:
    """测试评论解析"""
    
    @given(
        comment_count=st.integers(min_value=1, max_value=10),
        max_comments=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=30, deadline=5000)
    def test_comment_extraction_completeness(self, comment_count, max_comments):
        """
        测试评论提取完整性
        Feature: tencent-video-scraper, Property 9: 评论提取完整性
        """
        # 生成测试评论HTML
        html_parts = ["<html><body><div class='comment-list'>"]
        
        expected_comments = []
        for i in range(comment_count):
            author = f"用户{i+1}"
            content = f"这是第{i+1}条评论内容"
            time_str = "2024-01-01 12:00:00"
            
            html_parts.append(f"""
            <div class="comment-item">
                <div class="comment-author">{author}</div>
                <div class="comment-content">{content}</div>
                <div class="comment-time">{time_str}</div>
            </div>
            """)
            
            expected_comments.append({
                'author': author,
                'content': content,
                'time': time_str
            })
        
        html_parts.append("</div></body></html>")
        html = "".join(html_parts)
        
        parser = CommentParser()
        comments = parser.parse_comments(html, max_comments)
        
        # 验证评论数量不超过限制
        assert len(comments) <= max_comments, f"评论数量 {len(comments)} 不应超过限制 {max_comments}"
        
        # 验证评论数量符合预期
        expected_count = min(comment_count, max_comments)
        assert len(comments) == expected_count, \
            f"应该解析到 {expected_count} 条评论，实际得到 {len(comments)} 条"
        
        # 验证评论内容
        for i, comment in enumerate(comments):
            assert isinstance(comment.author, str), f"评论 {i} 的作者应该是字符串"
            assert isinstance(comment.content, str), f"评论 {i} 的内容应该是字符串"
            assert len(comment.content.strip()) > 0, f"评论 {i} 的内容不能为空"
    
    @given(
        raw_content=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        whitespace_type=st.sampled_from(['spaces', 'tabs', 'newlines', 'mixed'])
    )
    @settings(max_examples=30, deadline=5000)
    def test_comment_text_normalization(self, raw_content, whitespace_type):
        """
        测试评论文本标准化
        Feature: tencent-video-scraper, Property 10: 评论文本标准化
        """
        # 根据类型添加不同的空白字符
        if whitespace_type == 'spaces':
            messy_content = f"  {raw_content}  "
        elif whitespace_type == 'tabs':
            messy_content = f"\t{raw_content}\t"
        elif whitespace_type == 'newlines':
            messy_content = f"\n{raw_content}\n"
        else:  # mixed
            messy_content = f" \t\n {raw_content} \n\t "
        
        html = f"""
        <html>
        <body>
            <div class="comment-item">
                <div class="comment-author">测试用户</div>
                <div class="comment-content">{messy_content}</div>
                <div class="comment-time">2024-01-01</div>
            </div>
        </body>
        </html>
        """
        
        parser = CommentParser()
        comments = parser.parse_comments(html, 10)
        
        assert len(comments) > 0, "应该解析到至少一条评论"
        
        comment = comments[0]
        
        # 验证文本已被标准化
        assert comment.content.strip() == comment.content, "评论内容不应该有前后空白"
        assert '\t' not in comment.content, "评论内容不应该包含制表符"
        assert '\n' not in comment.content or comment.content.count('\n') <= 1, "评论内容不应该包含多余的换行符"
        
        # 验证核心内容保持不变
        normalized_raw = raw_content.strip()
        assert normalized_raw in comment.content or comment.content in normalized_raw, \
            f"标准化后的内容应该保持原始内容，原始: '{normalized_raw}'，处理后: '{comment.content}'"