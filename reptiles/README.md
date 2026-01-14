# 腾讯视频爬虫系统

一个功能完整的腾讯视频爬虫工具，支持视频信息提取、资源链接获取、SVIP内容绕过等功能。

## 功能特性

- 🎥 **视频信息提取**: 获取标题、描述、播放量、时长等完整信息
- 🔗 **视频链接获取**: 支持多画质视频源链接提取
- 👑 **SVIP内容绕过**: 绕过会员限制访问专享内容
- 📦 **批量处理**: 支持批量爬取多个视频
- 💾 **多格式输出**: 支持JSON、CSV、XML等格式
- 🚀 **高性能**: 异步处理，支持并发爬取
- 🛡️ **反爬虫处理**: 智能应对各种反爬虫机制
- 📊 **实时监控**: 提供详细的运行状态和统计信息

## 安装

```bash
pip install -r requirements.txt
python setup.py install
```

## 快速开始

```python
from tencent_video_scraper import ScraperEngine, ScraperConfig

# 创建配置
config = ScraperConfig(
    rate_limit=1.0,
    enable_comments=True,
    max_comments=50
)

# 创建爬虫引擎
scraper = ScraperEngine(config)

# 爬取单个视频
video_data = await scraper.scrape_video("https://v.qq.com/x/cover/xxx.html")
print(video_data.to_json())

# 批量爬取
urls = ["url1", "url2", "url3"]
results = await scraper.scrape_batch(urls)
```

## 配置选项

- `rate_limit`: 请求频率限制（每秒请求数）
- `timeout`: 请求超时时间
- `max_retries`: 最大重试次数
- `enable_comments`: 是否启用评论爬取
- `proxies`: 代理服务器列表
- `output_format`: 输出格式（json/csv/xml）

## 许可证

MIT License