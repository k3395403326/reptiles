"""测试SVIP视频解析"""
import asyncio
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from tencent_video_scraper.scraper import ScraperEngine
from tencent_video_scraper.models import ScraperConfig

async def test_svip_video():
    # 测试链接
    url = "https://v.qq.com/x/cover/ldl1811bamppdrd.html"
    
    print("=" * 50)
    print("🎬 测试SVIP视频解析")
    print(f"URL: {url}")
    print("=" * 50)
    
    # 创建配置
    config = ScraperConfig(
        timeout=30,
        max_retries=3,
        rate_limit=1.0
    )
    
    # 创建爬虫引擎
    engine = ScraperEngine(config)
    
    try:
        # 爬取视频
        result = await engine.scrape_video(url)
        
        print("\n✅ 解析成功!")
        print(f"标题: {result.title}")
        print(f"时长: {result.duration} 秒")
        print(f"播放量: {result.view_count}")
        print(f"是否SVIP: {result.is_svip}")
        print(f"缩略图: {result.thumbnail_url}")
        
        if result.video_urls:
            print(f"\n🎬 找到 {len(result.video_urls)} 个播放链接:")
            for i, video_url in enumerate(result.video_urls, 1):
                print(f"  {i}. [{video_url.quality}] {video_url.format}")
                print(f"     {video_url.url[:100]}...")
        else:
            print("\n⚠️ 未找到播放链接")
            
    except Exception as e:
        print(f"\n❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.close()

if __name__ == "__main__":
    asyncio.run(test_svip_video())
