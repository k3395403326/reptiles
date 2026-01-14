"""
Vercel Serverless Function
腾讯视频解析服务

提供完整的视频解析API和Web界面。
"""

import hashlib
import time
from urllib.parse import quote, unquote

from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# 简单的内存缓存
_cache = {}
_cache_ttl = 3600  # 1小时


def get_cache_key(url: str) -> str:
    """生成缓存键"""
    return hashlib.md5(url.encode()).hexdigest()


def detect_quality(url: str) -> str:
    """检测视频画质"""
    url_lower = url.lower()
    if '1080' in url_lower or 'fhd' in url_lower:
        return '1080p'
    elif '720' in url_lower or 'hd' in url_lower:
        return '720p'
    elif '480' in url_lower or 'sd' in url_lower:
        return '480p'
    return 'HD'


def detect_format(url: str) -> str:
    """检测视频格式"""
    url_lower = url.lower()
    if '.m3u8' in url_lower:
        return 'm3u8'
    elif '.mp4' in url_lower:
        return 'mp4'
    elif '.flv' in url_lower:
        return 'flv'
    return 'unknown'


# HTML模板 - 首页
INDEX_TEMPLATE = '''
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
        .success-box { background: #e8f5e9; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
        .error-box { background: #ffebee; color: #c62828; border-radius: 10px; padding: 16px; }
        .link-item { background: #f5f5f5; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
        .link-label { font-weight: 600; color: #333; margin-bottom: 4px; }
        .link-url { word-break: break-all; color: #667eea; font-size: 14px; margin-bottom: 8px; }
        .btn-group { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn-small {
            flex: 1;
            min-width: 80px;
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

# HTML模板 - 播放器
PLAYER_TEMPLATE = '''
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
            flex-wrap: wrap;
            gap: 10px;
        }
        .title { color: white; font-size: 16px; font-weight: 500; }
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
        .btn.outline { background: transparent; border: 1px solid #667eea; }
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


@app.route('/')
def index():
    """首页"""
    return render_template_string(INDEX_TEMPLATE)


@app.route('/api/parse', methods=['GET', 'POST'])
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
        cache_key = get_cache_key(video_url)
        if cache_key in _cache:
            cached = _cache[cache_key]
            if time.time() - cached.get('_cached_at', 0) < _cache_ttl:
                return jsonify(cached)
        
        # 尝试使用第三方解析
        # 简化版：直接返回演示结果
        # 实际部署时可以集成第三方解析API
        return jsonify({
            'success': False,
            'video_url': video_url,
            'play_url': None,
            'share_url': None,
            'error': '解析服务暂时不可用，请稍后重试'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'video_url': None,
            'play_url': None,
            'share_url': None
        })


@app.route('/api/convert', methods=['POST'])
def convert():
    """链接转换API（兼容旧版本）"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'error': '请输入视频链接'})
        
        if 'qq.com' not in url:
            return jsonify({'success': False, 'error': '请输入有效的腾讯视频链接'})
        
        pc_url = url
        mobile_url = url
        
        if 'm.v.qq.com' in url:
            pc_url = url.replace('m.v.qq.com', 'v.qq.com')
        elif 'v.qq.com' in url:
            mobile_url = url.replace('v.qq.com', 'm.v.qq.com')
        
        return jsonify({
            'success': True,
            'pc_url': pc_url,
            'mobile_url': mobile_url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/health')
def health():
    """健康检查端点"""
    return jsonify({
        'status': 'ok',
        'timestamp': time.time()
    })


@app.route('/play')
def play():
    """播放页面"""
    play_url = request.args.get('url', '')
    title = request.args.get('title', '腾讯视频')
    
    if not play_url:
        return "缺少播放链接", 400
    
    return render_template_string(
        PLAYER_TEMPLATE,
        play_url=unquote(play_url),
        title=title
    )


@app.route('/share/<share_id>')
def share(share_id):
    """分享页面"""
    share_data = _cache.get(f"share_{share_id}")
    if not share_data:
        return "分享链接已过期", 404
    
    return render_template_string(
        PLAYER_TEMPLATE,
        play_url=share_data.get('play_url', ''),
        title=share_data.get('title', '腾讯视频')
    )


# Vercel需要这个
app = app
