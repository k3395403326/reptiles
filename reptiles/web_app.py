"""
腾讯视频爬虫 Web 版本

提供简单的 Web 界面，支持手机浏览器访问。
"""

import sys
import logging
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTML 模板 - 响应式设计，支持手机
HTML_TEMPLATE = '''
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
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 24px;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        .input-group {
            margin-bottom: 16px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        input[type="text"] {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }
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
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        .result {
            margin-top: 20px;
            display: none;
        }
        .result.show { display: block; }
        .video-info {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .video-title {
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        .video-meta {
            color: #666;
            font-size: 14px;
        }
        .video-links {
            margin-top: 16px;
        }
        .video-link {
            display: block;
            padding: 12px 16px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            margin-bottom: 8px;
            text-align: center;
            font-weight: 500;
        }
        .video-link:hover {
            background: #5a6fd6;
        }
        .error {
            background: #fee;
            color: #c00;
            padding: 16px;
            border-radius: 10px;
            margin-top: 16px;
        }
        .loading {
            text-align: center;
            padding: 40px;
            display: none;
        }
        .loading.show { display: block; }
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .tips {
            color: rgba(255,255,255,0.8);
            text-align: center;
            font-size: 14px;
            margin-top: 20px;
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
        
        <p class="tips">💡 支持 v.qq.com 的视频链接</p>
    </div>

    <script>
        async function parseVideo() {
            const url = document.getElementById('url').value.trim();
            const btn = document.getElementById('parseBtn');
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');
            
            if (!url) {
                alert('请输入视频链接');
                return;
            }
            
            // 显示加载状态
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
                    showResult(data.data);
                } else {
                    showError(data.error || '解析失败');
                }
            } catch (error) {
                showError('网络错误: ' + error.message);
            } finally {
                btn.disabled = false;
                loading.classList.remove('show');
            }
        }
        
        function showResult(video) {
            const result = document.getElementById('result');
            
            // 生成手机端和电脑端网址
            let webLinksHtml = '';
            if (video.url) {
                const pcUrl = video.url;
                const mobileUrl = video.mobile_url || video.url.replace('v.qq.com', 'm.v.qq.com');
                webLinksHtml = `
                    <div class="video-links">
                        <p style="margin-bottom:8px;font-weight:600;">📱 网页链接:</p>
                        <a href="${pcUrl}" target="_blank" class="video-link" style="background:#4CAF50;">💻 电脑端网址</a>
                        <a href="${mobileUrl}" target="_blank" class="video-link" style="background:#2196F3;">📱 手机端网址</a>
                    </div>
                `;
            }
            
            let linksHtml = '';
            if (video.video_urls && video.video_urls.length > 0) {
                linksHtml = '<div class="video-links"><p style="margin-bottom:8px;font-weight:600;">🎬 播放链接:</p>';
                video.video_urls.forEach((v, i) => {
                    linksHtml += `<a href="${v.url}" target="_blank" class="video-link">${v.quality} - ${v.format}</a>`;
                });
                linksHtml += '</div>';
            } else {
                linksHtml = '<p style="color:#999;margin-top:16px;">未找到可用的播放链接</p>';
            }
            
            result.innerHTML = `
                <div class="video-info">
                    <div class="video-title">${video.title}</div>
                    <div class="video-meta">
                        时长: ${formatDuration(video.duration)} | 
                        播放: ${formatCount(video.view_count)}
                        ${video.is_svip ? ' | <span style="color:#ff9800">SVIP</span>' : ''}
                    </div>
                </div>
                ${webLinksHtml}
                ${linksHtml}
            `;
            result.classList.add('show');
        }
        
        function showError(message) {
            const result = document.getElementById('result');
            result.innerHTML = `<div class="error">❌ ${message}</div>`;
            result.classList.add('show');
        }
        
        function formatDuration(seconds) {
            if (!seconds) return '未知';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = seconds % 60;
            if (h > 0) return `${h}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
            return `${m}:${s.toString().padStart(2,'0')}`;
        }
        
        function formatCount(count) {
            if (!count) return '0';
            if (count >= 100000000) return (count / 100000000).toFixed(1) + '亿';
            if (count >= 10000) return (count / 10000).toFixed(1) + '万';
            return count.toString();
        }
        
        // 回车键触发解析
        document.getElementById('url').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') parseVideo();
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """首页"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/parse', methods=['POST'])
def parse_video():
    """解析视频 API"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'error': '请输入视频链接'})
        
        if 'qq.com' not in url:
            return jsonify({'success': False, 'error': '请输入有效的腾讯视频链接'})
        
        # 直接生成手机端和电脑端链接
        pc_url = url
        mobile_url = url
        
        # 转换为电脑端链接
        if 'm.v.qq.com' in url:
            pc_url = url.replace('m.v.qq.com', 'v.qq.com')
            mobile_url = url
        # 转换为手机端链接
        elif 'v.qq.com' in url:
            pc_url = url
            mobile_url = url.replace('v.qq.com', 'm.v.qq.com')
        
        # 返回简单结果
        return jsonify({
            'success': True,
            'data': {
                'url': url,
                'pc_url': pc_url,
                'mobile_url': mobile_url,
                'title': '腾讯视频',
                'duration': 0,
                'view_count': 0,
                'is_svip': False,
                'video_urls': []
            }
        })
        
    except Exception as e:
        logger.exception("解析失败")
        return jsonify({
            'success': False,
            'error': str(e)
        })


def get_local_ip():
    """获取本机局域网IP"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ngrok', action='store_true', help='启用ngrok公网访问')
    parser.add_argument('--port', type=int, default=5000, help='端口号')
    args = parser.parse_args()
    
    local_ip = get_local_ip()
    
    print("=" * 50)
    print("🎬 腾讯视频解析 Web 服务")
    print("=" * 50)
    print()
    print(f"本机访问: http://127.0.0.1:{args.port}")
    print(f"局域网访问: http://{local_ip}:{args.port}")
    
    # 尝试启动 ngrok
    if args.ngrok:
        try:
            from pyngrok import ngrok
            public_url = ngrok.connect(args.port)
            print()
            print("=" * 50)
            print(f"🌐 公网访问链接: {public_url}")
            print("任何设备都可以通过此链接访问！")
            print("=" * 50)
        except ImportError:
            print()
            print("⚠️ 未安装 pyngrok，请运行: pip install pyngrok")
            print("或手动运行: ngrok http 5000")
        except Exception as e:
            print(f"⚠️ ngrok 启动失败: {e}")
    else:
        print()
        print("💡 提示: 运行 python web_app.py --ngrok 可获取公网链接")
    
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=args.port, debug=False)
