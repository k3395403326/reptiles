"""
Web服务模块

提供HTTP API接口和Web界面供用户访问视频解析功能。
"""

import asyncio
import logging
import json
import hashlib
import time
from typing import Optional, Dict, Any
from urllib.parse import quote, unquote
from flask import Flask, render_template_string, request, jsonify, redirect, url_for

from .models import ScraperConfig
from .http_client import HTTPClient
from .svip_handler import SVIPHandler, ThirdPartyParseStrategy
from .third_party_parser import ThirdPartyParserManager

logger = logging.getLogger(__name__)


class WebService:
    """Web服务，提供HTTP API和Web界面"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        """
        初始化Web服务
        
        Args:
            config: 爬虫配置
        """
        self.config = config or ScraperConfig()
        self.app = Flask(__name__)
        self.http_client: Optional[HTTPClient] = None
        self.svip_handler: Optional[SVIPHandler] = None
        self.parser_manager: Optional[ThirdPartyParserManager] = None
        
        # 缓存解析结果
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 3600  # 缓存1小时
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册Flask路由"""
        
        @self.app.route('/')
        def index():
            """首页 - 视频URL输入"""
            return render_template_string(self._get_index_template())
        
        @self.app.route('/api/parse', methods=['GET', 'POST'])
        def api_parse():
            """解析视频API端点"""
            try:
                if request.method == 'POST':
                    data = request.get_json() or {}
                    video_url = data.get('url', '').strip()
                else:
                    video_url = request.args.get('url', '').strip()
                
                if not video_url:
                    return jsonify({
                        'success': False,
                        'error': '请提供视频URL',
                        'video_url': None,
                        'play_url': None,
                        'share_url': None
                    })
                
                if 'qq.com' not in video_url:
                    return jsonify({
                        'success': False,
                        'error': '请输入有效的腾讯视频链接',
                        'video_url': video_url,
                        'play_url': None,
                        'share_url': None
                    })
                
                # 检查缓存
                cache_key = self._get_cache_key(video_url)
                cached = self._get_cached_result(cache_key)
                if cached:
                    return jsonify(cached)
                
                # 解析视频
                result = self._parse_video_sync(video_url)
                
                # 缓存结果
                if result.get('success'):
                    self._cache_result(cache_key, result)
                
                return jsonify(result)
                
            except Exception as e:
                logger.exception("API解析失败")
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'video_url': None,
                    'play_url': None,
                    'share_url': None
                })
        
        @self.app.route('/play')
        def play():
            """播放页面"""
            play_url = request.args.get('url', '')
            title = request.args.get('title', '腾讯视频')
            
            if not play_url:
                return "缺少播放链接", 400
            
            return render_template_string(
                self._get_player_template(),
                play_url=unquote(play_url),
                title=title
            )
        
        @self.app.route('/share/<share_id>')
        def share(share_id):
            """分享页面"""
            # 从缓存中获取分享信息
            share_data = self._cache.get(f"share_{share_id}")
            if not share_data:
                return "分享链接已过期", 404
            
            return render_template_string(
                self._get_player_template(),
                play_url=share_data.get('play_url', ''),
                title=share_data.get('title', '腾讯视频')
            )
        
        @self.app.route('/api/health')
        def health():
            """健康检查端点"""
            return jsonify({
                'status': 'ok',
                'timestamp': time.time()
            })
    
    def _parse_video_sync(self, video_url: str) -> Dict[str, Any]:
        """同步解析视频（在Flask中使用）"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._parse_video_async(video_url))
        finally:
            loop.close()
    
    async def _parse_video_async(self, video_url: str) -> Dict[str, Any]:
        """异步解析视频"""
        try:
            # 初始化组件
            if not self.http_client:
                self.http_client = HTTPClient(self.config)
            
            if not self.parser_manager:
                self.parser_manager = ThirdPartyParserManager(self.config)
            
            # 使用第三方解析器解析
            play_url = await self.parser_manager.parse(video_url, self.http_client)
            
            if play_url:
                # 生成分享链接
                share_url = self._generate_share_url(play_url, "腾讯视频")
                
                return {
                    'success': True,
                    'video_url': video_url,
                    'play_url': play_url,
                    'share_url': share_url,
                    'quality': self._detect_quality(play_url),
                    'format': self._detect_format(play_url),
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'video_url': video_url,
                    'play_url': None,
                    'share_url': None,
                    'error': '解析失败，所有解析渠道都无法获取播放链接'
                }
                
        except Exception as e:
            logger.exception("解析视频失败")
            return {
                'success': False,
                'video_url': video_url,
                'play_url': None,
                'share_url': None,
                'error': str(e)
            }
    
    def _generate_share_url(self, play_url: str, title: str) -> str:
        """生成可分享的播放页面链接"""
        # 生成分享ID
        share_id = hashlib.md5(f"{play_url}{time.time()}".encode()).hexdigest()[:12]
        
        # 缓存分享信息
        self._cache[f"share_{share_id}"] = {
            'play_url': play_url,
            'title': title,
            'created_at': time.time()
        }
        
        # 返回分享URL（相对路径，部署时会自动加上域名）
        return f"/share/{share_id}"
    
    def _detect_quality(self, url: str) -> str:
        """检测视频画质"""
        url_lower = url.lower()
        if '1080' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        return 'unknown'
    
    def _detect_format(self, url: str) -> str:
        """检测视频格式"""
        url_lower = url.lower()
        if '.m3u8' in url_lower:
            return 'm3u8'
        elif '.mp4' in url_lower:
            return 'mp4'
        elif '.flv' in url_lower:
            return 'flv'
        return 'unknown'
    
    def _get_cache_key(self, url: str) -> str:
        """生成缓存键"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取缓存的结果"""
        cached = self._cache.get(cache_key)
        if cached:
            if time.time() - cached.get('_cached_at', 0) < self._cache_ttl:
                return cached
            else:
                del self._cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """缓存结果"""
        result['_cached_at'] = time.time()
        self._cache[cache_key] = result

    
    def _get_index_template(self) -> str:
        """获取首页HTML模板"""
        return '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>腾讯视频解析</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { color: white; text-align: center; margin-bottom: 30px; font-size: 28px; }
        .card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        .input-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
        input[type="text"] {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus { outline: none; border-color: #667eea; }
        button {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4); }
        button:disabled { background: #ccc; cursor: not-allowed; transform: none; }
        .result { margin-top: 20px; display: none; }
        .result.show { display: block; }
        .success-box {
            background: #e8f5e9;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .error-box {
            background: #ffebee;
            color: #c62828;
            border-radius: 10px;
            padding: 16px;
        }
        .link-item {
            background: #f5f5f5;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .link-label { font-weight: 600; color: #333; margin-bottom: 4px; }
        .link-url {
            word-break: break-all;
            color: #667eea;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .btn-group { display: flex; gap: 8px; }
        .btn-small {
            flex: 1;
            padding: 8px 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
        }
        .btn-small:hover { background: #5a6fd6; }
        .btn-small.green { background: #4caf50; }
        .btn-small.green:hover { background: #43a047; }
        .loading { text-align: center; padding: 30px; display: none; }
        .loading.show { display: block; }
        .spinner {
            width: 40px; height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .tips { color: rgba(255,255,255,0.8); text-align: center; font-size: 14px; margin-top: 20px; }
        .quality-badge {
            display: inline-block;
            padding: 2px 8px;
            background: #667eea;
            color: white;
            border-radius: 4px;
            font-size: 12px;
            margin-left: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 腾讯视频解析</h1>
        <div class="card">
            <div class="input-group">
                <label>视频链接</label>
                <input type="text" id="url" placeholder="粘贴腾讯视频链接...">
            </div>
            <button id="parseBtn" onclick="parseVideo()">解析视频</button>
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>正在解析，请稍候...</p>
            </div>
            <div class="result" id="result"></div>
        </div>
        <p class="tips">💡 支持 v.qq.com 的视频链接，包括SVIP内容</p>
    </div>
    <script>
        async function parseVideo() {
            const url = document.getElementById('url').value.trim();
            const btn = document.getElementById('parseBtn');
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');
            
            if (!url) { alert('请输入视频链接'); return; }
            
            btn.disabled = true;
            loading.classList.add('show');
            result.classList.remove('show');
            
            try {
                const response = await fetch('/api/parse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await response.json();
                
                if (data.success) {
                    result.innerHTML = `
                        <div class="success-box">
                            <p style="color:#2e7d32;font-weight:600;margin-bottom:12px;">✅ 解析成功</p>
                            <div class="link-item">
                                <div class="link-label">播放链接 <span class="quality-badge">${data.quality || 'HD'}</span></div>
                                <div class="link-url" id="playUrl">${data.play_url}</div>
                                <div class="btn-group">
                                    <button class="btn-small" onclick="copyText('playUrl')">复制链接</button>
                                    <a class="btn-small green" href="/play?url=${encodeURIComponent(data.play_url)}&title=腾讯视频" target="_blank">在线播放</a>
                                </div>
                            </div>
                            <div class="link-item">
                                <div class="link-label">分享链接</div>
                                <div class="link-url" id="shareUrl">${window.location.origin}${data.share_url}</div>
                                <div class="btn-group">
                                    <button class="btn-small" onclick="copyText('shareUrl')">复制分享链接</button>
                                    <button class="btn-small" style="background:#25D366" onclick="shareToWhatsApp()">WhatsApp</button>
                                    <button class="btn-small" style="background:#1DA1F2" onclick="shareToTwitter()">Twitter</button>
                                </div>
                            </div>
                        </div>
                    `;
                    // 保存分享URL供社交分享使用
                    window.currentShareUrl = window.location.origin + data.share_url;
                } else {
                    result.innerHTML = `<div class="error-box">❌ ${data.error}</div>`;
                }
                result.classList.add('show');
            } catch (e) {
                result.innerHTML = `<div class="error-box">❌ 网络错误: ${e.message}</div>`;
                result.classList.add('show');
            } finally {
                btn.disabled = false;
                loading.classList.remove('show');
            }
        }
        
        function copyText(id) {
            const text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text).then(() => alert('已复制到剪贴板'));
        }
        
        function shareToWhatsApp() {
            const url = window.currentShareUrl || window.location.href;
            const text = encodeURIComponent('来看这个视频: ' + url);
            window.open('https://wa.me/?text=' + text, '_blank');
        }
        
        function shareToTwitter() {
            const url = window.currentShareUrl || window.location.href;
            const text = encodeURIComponent('来看这个视频');
            window.open('https://twitter.com/intent/tweet?text=' + text + '&url=' + encodeURIComponent(url), '_blank');
        }
        
        document.getElementById('url').addEventListener('keypress', e => {
            if (e.key === 'Enter') parseVideo();
        });
    </script>
</body>
</html>
'''
    
    def _get_player_template(self) -> str:
        """获取播放器HTML模板"""
        return '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - 在线播放</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #000;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .player-container {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        video {
            max-width: 100%;
            max-height: 80vh;
            background: #000;
        }
        .controls {
            background: #1a1a1a;
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .title {
            color: white;
            font-size: 16px;
            font-weight: 500;
        }
        .btn-group { display: flex; gap: 10px; }
        .btn {
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
        }
        .btn:hover { background: #5a6fd6; }
        .btn.outline {
            background: transparent;
            border: 1px solid #667eea;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
</head>
<body>
    <div class="player-container">
        <video id="video" controls autoplay playsinline></video>
    </div>
    <div class="controls">
        <div class="title">{{ title }}</div>
        <div class="btn-group">
            <button class="btn outline" onclick="copyLink()">复制链接</button>
            <button class="btn" onclick="toggleFullscreen()">全屏</button>
        </div>
    </div>
    <script>
        const video = document.getElementById('video');
        const playUrl = '{{ play_url }}';
        
        // 检测是否为m3u8格式
        if (playUrl.includes('.m3u8')) {
            if (Hls.isSupported()) {
                const hls = new Hls();
                hls.loadSource(playUrl);
                hls.attachMedia(video);
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = playUrl;
            }
        } else {
            video.src = playUrl;
        }
        
        function copyLink() {
            navigator.clipboard.writeText(window.location.href).then(() => alert('链接已复制'));
        }
        
        function toggleFullscreen() {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                video.requestFullscreen();
            }
        }
    </script>
</body>
</html>
'''
    
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
        """运行Web服务"""
        logger.info(f"启动Web服务: http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)
    
    def get_app(self):
        """获取Flask应用实例（用于WSGI部署）"""
        return self.app
    
    async def cleanup(self):
        """清理资源"""
        if self.http_client:
            await self.http_client.close()


def create_app(config: Optional[ScraperConfig] = None) -> Flask:
    """创建Flask应用（工厂函数）"""
    service = WebService(config)
    return service.get_app()
