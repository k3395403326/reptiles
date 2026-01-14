# 部署指南

本文档介绍如何将腾讯视频解析服务部署到各种平台。

## Vercel 部署

### 方法一：一键部署

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/your-repo/tencent-video-scraper)

### 方法二：手动部署

1. 安装 Vercel CLI：
```bash
npm i -g vercel
```

2. 登录 Vercel：
```bash
vercel login
```

3. 部署项目：
```bash
vercel
```

4. 部署到生产环境：
```bash
vercel --prod
```

### 配置说明

项目根目录的 `vercel.json` 已配置好所有路由：
- `/` - 首页
- `/api/parse` - 解析API
- `/play` - 播放页面
- `/share/*` - 分享页面

## Gitee Pages 部署

Gitee Pages 只支持静态页面，因此只能部署链接转换功能（无需后端）。

1. 在 Gitee 创建仓库

2. 将 `gitee-deploy/index.html` 上传到仓库

3. 进入仓库设置 -> 服务 -> Gitee Pages

4. 选择部署分支和目录，点击启动

5. 访问生成的 Gitee Pages 链接

## 本地运行

### 使用 Flask 开发服务器

```bash
# 安装依赖
pip install -r requirements.txt

# 运行服务
python -m tencent_video_scraper.cli web --port 5000
```

### 使用 web_app.py

```bash
python web_app.py --port 5000
```

### 启用公网访问（ngrok）

```bash
# 安装 pyngrok
pip install pyngrok

# 运行服务并启用 ngrok
python web_app.py --ngrok
```

## Docker 部署

创建 `Dockerfile`：

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["python", "-m", "tencent_video_scraper.cli", "web", "--port", "5000"]
```

构建和运行：

```bash
docker build -t tencent-video-scraper .
docker run -p 5000:5000 tencent-video-scraper
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| PORT | 服务端口 | 5000 |
| DEBUG | 调试模式 | false |

## 注意事项

1. Vercel 免费版有执行时间限制（10秒），复杂解析可能超时
2. Gitee Pages 只支持静态页面，无法使用解析功能
3. 建议使用自己的服务器部署以获得最佳体验
