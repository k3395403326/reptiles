#!/usr/bin/env python3
"""
HTTP客户端和代理管理器演示脚本

演示HTTP客户端的基本功能和代理管理器的集成。
"""

import asyncio
import logging
from tencent_video_scraper.models import ScraperConfig
from tencent_video_scraper.http_client import HTTPClient

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def demo_http_client():
    """演示HTTP客户端功能"""
    print("=== HTTP客户端和代理管理器演示 ===\n")
    
    # 创建配置
    config = ScraperConfig(
        rate_limit=2.0,  # 每秒2个请求
        timeout=10,
        max_retries=2,
        enable_detailed_logs=True,
        proxies=[
            # 这些是示例代理，实际使用时需要替换为有效代理
            # 'http://proxy1.example.com:8080',
            # 'http://proxy2.example.com:8080'
        ],
        user_agents=[
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
    )
    
    # 创建HTTP客户端
    client = HTTPClient(config)
    
    try:
        # 启动客户端（如果有代理管理器会启动健康检查）
        await client.start()
        
        print("1. 测试基本HTTP请求")
        print("-" * 30)
        
        # 测试请求
        test_urls = [
            'http://httpbin.org/ip',
            'http://httpbin.org/user-agent',
            'http://httpbin.org/headers'
        ]
        
        for i, url in enumerate(test_urls, 1):
            print(f"\n请求 {i}: {url}")
            
            try:
                response = await client.get(url)
                if response:
                    print(f"✓ 状态码: {response.status}")
                    print(f"✓ 响应长度: {len(response._content)} 字符")
                    
                    # 显示部分响应内容
                    content_preview = response._content[:200]
                    if len(response._content) > 200:
                        content_preview += "..."
                    print(f"✓ 响应预览: {content_preview}")
                else:
                    print("✗ 请求失败")
                    
            except Exception as e:
                print(f"✗ 请求异常: {e}")
            
            # 等待一下以遵守速率限制
            await asyncio.sleep(0.5)
        
        print("\n\n2. 测试请求头轮换")
        print("-" * 30)
        
        # 测试User-Agent轮换
        user_agents_seen = set()
        for i in range(5):
            headers = client._build_headers()
            user_agent = headers['User-Agent']
            user_agents_seen.add(user_agent)
            print(f"请求 {i+1} User-Agent: {user_agent[:50]}...")
        
        print(f"\n✓ 使用了 {len(user_agents_seen)} 个不同的User-Agent")
        
        print("\n\n3. 测试统计信息")
        print("-" * 30)
        
        stats = client.get_stats()
        print(f"总请求数: {stats['total_requests']}")
        print(f"成功请求数: {stats['successful_requests']}")
        print(f"失败请求数: {stats['failed_requests']}")
        print(f"成功率: {stats['success_rate']:.2%}")
        
        if client.proxy_manager:
            print("\n4. 代理管理器统计")
            print("-" * 30)
            
            proxy_stats = client.proxy_manager.get_proxy_stats()
            print(f"代理总数: {proxy_stats['total']}")
            print(f"活跃代理: {proxy_stats['active']}")
            print(f"失败代理: {proxy_stats['failed']}")
            print(f"封禁代理: {proxy_stats['banned']}")
        else:
            print("\n4. 未配置代理管理器")
        
        print("\n\n5. 测试错误处理")
        print("-" * 30)
        
        # 测试无效URL
        invalid_url = "http://this-domain-does-not-exist-12345.com"
        print(f"测试无效URL: {invalid_url}")
        
        response = await client.get(invalid_url)
        if response:
            print("✗ 意外成功")
        else:
            print("✓ 正确处理了无效URL")
        
        # 最终统计
        final_stats = client.get_stats()
        print(f"\n最终统计:")
        print(f"总请求数: {final_stats['total_requests']}")
        print(f"成功率: {final_stats['success_rate']:.2%}")
        
    finally:
        # 清理资源
        await client.close()
        print("\n✓ HTTP客户端已关闭")


async def demo_proxy_manager():
    """演示代理管理器功能"""
    print("\n\n=== 代理管理器独立演示 ===\n")
    
    from tencent_video_scraper.proxy_manager import ProxyManager
    
    # 创建示例代理列表
    test_proxies = [
        'http://proxy1.example.com:8080',
        'http://proxy2.example.com:8080',
        'http://proxy3.example.com:8080'
    ]
    
    manager = ProxyManager(test_proxies, check_interval=60)
    
    print("1. 代理管理器初始化")
    print("-" * 30)
    
    stats = manager.get_proxy_stats()
    print(f"初始代理数量: {stats['total']}")
    print(f"活跃代理数量: {stats['active']}")
    
    print("\n2. 代理选择测试")
    print("-" * 30)
    
    for i in range(5):
        proxy = manager.get_active_proxy()
        print(f"选择的代理 {i+1}: {proxy}")
    
    print("\n3. 代理失败处理测试")
    print("-" * 30)
    
    # 模拟代理失败
    test_proxy = test_proxies[0]
    print(f"模拟代理失败: {test_proxy}")
    
    for i in range(3):
        manager.mark_proxy_failed(test_proxy)
        proxy_info = manager.proxies[test_proxy]
        print(f"失败次数 {i+1}: 状态={proxy_info.status.value}, 失败计数={proxy_info.failure_count}")
    
    print("\n4. IP封禁检测测试")
    print("-" * 30)
    
    # 测试不同的响应
    test_cases = [
        (403, "访问被拒绝"),
        (429, "too many requests"),
        (200, "正常响应"),
        (500, "服务器错误")
    ]
    
    for status_code, response_text in test_cases:
        is_banned = manager.detect_ip_ban(response_text, status_code)
        print(f"状态码 {status_code}, 响应 '{response_text}': {'封禁' if is_banned else '正常'}")
    
    print("\n5. 最终统计")
    print("-" * 30)
    
    final_stats = manager.get_proxy_stats()
    for key, value in final_stats.items():
        print(f"{key}: {value}")


async def main():
    """主函数"""
    try:
        await demo_http_client()
        await demo_proxy_manager()
        
        print("\n" + "="*50)
        print("✓ 演示完成！HTTP客户端和代理管理器工作正常。")
        print("="*50)
        
    except Exception as e:
        print(f"\n✗ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())