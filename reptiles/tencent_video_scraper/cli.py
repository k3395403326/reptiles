"""
命令行界面

提供命令行参数解析和交互式配置。
"""

import argparse
import asyncio
import sys
import logging
from typing import List, Optional

from .scraper import ScraperEngine, AdvancedScraperEngine
from .models import ScraperConfig
from .config_manager import ConfigManager, LogManager
from .storage_manager import StorageManager
from .downloader import VideoDownloader
from .monitor import MonitorManager, ControlManager


logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='tencent-video-scraper',
        description='腾讯视频爬虫工具 - 提取视频信息和播放链接',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s https://v.qq.com/x/cover/xxx.html
  %(prog)s -f urls.txt -o json --comments
  %(prog)s --config config.json
  %(prog)s --generate-config
        '''
    )
    
    # 位置参数
    parser.add_argument(
        'urls',
        nargs='*',
        help='要爬取的视频URL列表'
    )
    
    # 输入选项
    input_group = parser.add_argument_group('输入选项')
    input_group.add_argument(
        '-f', '--file',
        help='从文件读取URL列表（每行一个URL）'
    )
    input_group.add_argument(
        '-c', '--config',
        help='配置文件路径'
    )
    
    # 输出选项
    output_group = parser.add_argument_group('输出选项')
    output_group.add_argument(
        '-o', '--output-format',
        choices=['json', 'csv', 'xml'],
        default='json',
        help='输出格式（默认: json）'
    )
    output_group.add_argument(
        '-d', '--output-dir',
        default='./output',
        help='输出目录（默认: ./output）'
    )
    
    # 爬取选项
    scrape_group = parser.add_argument_group('爬取选项')
    scrape_group.add_argument(
        '--comments',
        action='store_true',
        help='同时爬取评论'
    )
    scrape_group.add_argument(
        '--max-comments',
        type=int,
        default=100,
        help='最大评论数量（默认: 100）'
    )
    scrape_group.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='每秒请求数（默认: 1.0）'
    )
    scrape_group.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='请求超时时间（秒，默认: 30）'
    )
    scrape_group.add_argument(
        '--retries',
        type=int,
        default=3,
        help='最大重试次数（默认: 3）'
    )
    
    # 下载选项
    download_group = parser.add_argument_group('下载选项')
    download_group.add_argument(
        '--download',
        action='store_true',
        help='下载视频文件'
    )
    download_group.add_argument(
        '--quality',
        choices=['best', '1080p', '720p', '480p'],
        default='best',
        help='下载画质（默认: best）'
    )
    download_group.add_argument(
        '--download-dir',
        default='./downloads',
        help='下载目录（默认: ./downloads）'
    )
    
    # 代理选项
    proxy_group = parser.add_argument_group('代理选项')
    proxy_group.add_argument(
        '--proxy',
        action='append',
        help='代理服务器（可多次指定）'
    )
    proxy_group.add_argument(
        '--proxy-file',
        help='代理列表文件'
    )
    
    # 其他选项
    other_group = parser.add_argument_group('其他选项')
    other_group.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    other_group.add_argument(
        '--log-file',
        help='日志文件路径'
    )
    other_group.add_argument(
        '--generate-config',
        action='store_true',
        help='生成配置模板文件'
    )
    other_group.add_argument(
        '--advanced',
        action='store_true',
        help='使用高级爬虫引擎（支持并发和重试）'
    )
    
    return parser


def load_urls_from_file(filepath: str) -> List[str]:
    """从文件加载URL列表"""
    urls = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
        return urls
    except Exception as e:
        logger.error(f"读取URL文件失败: {e}")
        return []


def load_proxies_from_file(filepath: str) -> List[str]:
    """从文件加载代理列表"""
    proxies = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    proxies.append(line)
        return proxies
    except Exception as e:
        logger.error(f"读取代理文件失败: {e}")
        return []


def build_config(args) -> ScraperConfig:
    """从命令行参数构建配置"""
    # 如果指定了配置文件，先加载
    if args.config:
        config_manager = ConfigManager(args.config)
        config = config_manager.get_config()
    else:
        config = ScraperConfig()
    
    # 覆盖命令行参数
    config.output_format = args.output_format
    config.download_path = args.download_dir
    config.enable_comments = args.comments
    config.max_comments = args.max_comments
    config.rate_limit = args.rate_limit
    config.timeout = args.timeout
    config.max_retries = args.retries
    config.enable_download = args.download
    config.enable_detailed_logs = args.verbose
    
    # 加载代理
    proxies = []
    if args.proxy:
        proxies.extend(args.proxy)
    if args.proxy_file:
        proxies.extend(load_proxies_from_file(args.proxy_file))
    if proxies:
        config.proxies = proxies
    
    return config


async def run_scraper(args):
    """运行爬虫"""
    # 收集URL
    urls = list(args.urls) if args.urls else []
    if args.file:
        urls.extend(load_urls_from_file(args.file))
    
    if not urls:
        print("错误: 没有指定要爬取的URL")
        print("使用 --help 查看帮助信息")
        return 1
    
    # 构建配置
    config = build_config(args)
    
    # 设置日志
    log_manager = LogManager(config)
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_manager.setup_logging(args.log_file, log_level)
    
    # 创建爬虫引擎
    if args.advanced:
        engine = AdvancedScraperEngine(config)
        print("使用高级爬虫引擎")
    else:
        engine = ScraperEngine(config)
    
    # 创建存储管理器
    storage = StorageManager(config)
    
    # 创建监控器
    monitor = MonitorManager(config)
    monitor.start()
    
    # 进度显示
    def show_progress(update):
        if update.get('type') == 'batch_progress':
            current = update['current']
            total = update['total']
            progress = update['progress']
            print(f"\r进度: {current}/{total} ({progress:.1%})", end='', flush=True)
        elif update.get('type') == 'video_completed':
            print(f"\n✓ {update['title']}")
        elif update.get('type') == 'video_failed':
            print(f"\n✗ 失败: {update['error']}")
    
    engine.set_progress_callback(show_progress)
    
    try:
        print(f"开始爬取 {len(urls)} 个视频...")
        
        # 执行爬取
        if args.advanced:
            results = await engine.scrape_batch_concurrent(urls)
        else:
            results = await engine.scrape_batch(urls)
        
        print(f"\n\n爬取完成: 成功 {len(results)}/{len(urls)} 个视频")
        
        # 保存结果
        if results:
            filepath = storage.save_batch_data(results)
            print(f"数据已保存到: {filepath}")
        
        # 下载视频
        if args.download and results:
            print("\n开始下载视频...")
            downloader = VideoDownloader(config)
            downloaded = await downloader.download_batch(results, args.quality)
            print(f"下载完成: {len(downloaded)} 个文件")
        
        # 显示统计
        stats = engine.get_stats()
        print(f"\n统计信息:")
        print(f"  总请求数: {stats.get('total_videos', 0)}")
        print(f"  成功率: {stats.get('success_rate', 0):.1%}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
        return 130
        
    except Exception as e:
        print(f"\n错误: {e}")
        logger.exception("爬虫执行失败")
        return 1
        
    finally:
        await engine.close()
        monitor.stop()


def main():
    """主入口函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 生成配置模板
    if args.generate_config:
        config_manager = ConfigManager()
        filepath = config_manager.generate_template()
        print(f"配置模板已生成: {filepath}")
        return 0
    
    # 运行爬虫
    try:
        # Windows 上使用 WindowsSelectorEventLoopPolicy 避免关闭时的警告
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        return asyncio.run(run_scraper(args))
    except Exception as e:
        print(f"错误: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())