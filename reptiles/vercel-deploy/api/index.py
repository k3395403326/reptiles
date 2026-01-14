"""
Vercel Serverless Function
腾讯视频链接转换工具
"""

from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# HTML 模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>腾讯视频链接转换</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { color: white; text-align: center; margin-bottom: 30px; font-size: 24px; }
        .card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .input-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
        input[type="text"] {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
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
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4); }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .result { margin-top: 20px; display: none; }
        .result.show { display: block; }
        .link-box {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .link-title { font-weight: 600; color: #333; margin-bottom: 8px; }
        .link-url {
            word-break: break-all;
            color: #667eea;
            font-size: 14px;
        }
        .copy-btn {
            display: inline-block;
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            cursor: pointer;
            margin-top: 8px;
        }
        .copy-btn:hover { background: #5a6fd6; }
        .error { background: #fee; color: #c00; padding: 16px; border-radius: 10px; }
        .tips { color: rgba(255,255,255,0.8); text-align: center; font-size: 14px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 腾讯视频链接转换</h1>
        <div class="card">
            <div class="input-group">
                <label>视频链接</label>
                <input type="text" id="url" placeholder="粘贴腾讯视频链接...">
            </div>
            <button onclick="convert()">转换链接</button>
            <div class="result" id="result"></div>
        </div>
        <p class="tips">💡 输入腾讯视频链接，获取手机端和电脑端网址</p>
    </div>
    <script>
        async function convert() {
            const url = document.getElementById('url').value.trim();
            const result = document.getElementById('result');
            if (!url) { alert('请输入视频链接'); return; }
            
            try {
                const response = await fetch('/api/convert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await response.json();
                if (data.success) {
                    result.innerHTML = `
                        <div class="link-box">
                            <div class="link-title">💻 电脑端网址</div>
                            <div class="link-url" id="pcUrl">${data.pc_url}</div>
                            <button class="copy-btn" onclick="copyText('pcUrl')">复制链接</button>
                        </div>
                        <div class="link-box">
                            <div class="link-title">📱 手机端网址</div>
                            <div class="link-url" id="mobileUrl">${data.mobile_url}</div>
                            <button class="copy-btn" onclick="copyText('mobileUrl')">复制链接</button>
                        </div>
                    `;
                    result.classList.add('show');
                } else {
                    result.innerHTML = '<div class="error">❌ ' + data.error + '</div>';
                    result.classList.add('show');
                }
            } catch (e) {
                result.innerHTML = '<div class="error">❌ 网络错误</div>';
                result.classList.add('show');
            }
        }
        
        function copyText(id) {
            const text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text).then(() => {
                alert('已复制到剪贴板');
            });
        }
        
        document.getElementById('url').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') convert();
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/convert', methods=['POST'])
def convert():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'error': '请输入视频链接'})
        
        if 'qq.com' not in url:
            return jsonify({'success': False, 'error': '请输入有效的腾讯视频链接'})
        
        # 转换链接
        pc_url = url
        mobile_url = url
        
        if 'm.v.qq.com' in url:
            pc_url = url.replace('m.v.qq.com', 'v.qq.com')
            mobile_url = url
        elif 'v.qq.com' in url:
            pc_url = url
            mobile_url = url.replace('v.qq.com', 'm.v.qq.com')
        
        return jsonify({
            'success': True,
            'pc_url': pc_url,
            'mobile_url': mobile_url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Vercel 需要这个
app = app
