#!/usr/bin/env python3
"""
启动 RedNote 爬虫脚本
支持持久化浏览器状态，避免每次重新登录
"""
import asyncio
import json
import sys
from pathlib import Path
from crawl4ai.crawlers.rednote.crawler import RedNoteCrawler


async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 RedNote 爬虫启动")
    print("=" * 70)
    
    # 创建爬虫实例
    crawler = RedNoteCrawler()
    
    print(f"\n📁 浏览器状态目录: {crawler.browser_data_dir}")
    print(f"📁 数据存储目录: {crawler.storage_dir}")
    
    # 检查是否已有浏览器状态
    if crawler.browser_data_dir.exists() and any(crawler.browser_data_dir.iterdir()):
        print("✅ 检测到已保存的浏览器状态")
        print("   - 登录状态将自动恢复")
        print("   - 无需手动登录（除非会话已过期）")
    else:
        print("ℹ️  首次运行")
        print("   - 浏览器窗口打开后，请手动登录")
        print("   - 登录状态将自动保存，下次运行无需再登录")
    
    print("\n" + "=" * 70)
    print("📋 爬取配置:")
    print("   - 搜索关键词: 牛奶")
    print("   - 爬取数量: 5 个笔记（第一排）")
    print("   - 筛选条件: 最多点赞")
    print("=" * 70)
    
    print("\n⏳ 5秒后启动浏览器... (按 Ctrl+C 取消)")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...", end='\r')
            await asyncio.sleep(1)
        print("   🚀 启动中...")
    except KeyboardInterrupt:
        print("\n\n❌ 已取消")
        return
    
    try:
        # 运行爬虫
        print("\n" + "=" * 70)
        print("🔄 开始爬取...")
        print("=" * 70)
        
        result = await crawler.run(
            search_keyword="牛奶",
            max_notes=5,
            headless=False,  # 非无头模式，可以看到浏览器
            verbose=True
        )
        
        # 解析结果
        data = json.loads(result)
        
        print("\n" + "=" * 70)
        print("📊 爬取结果")
        print("=" * 70)
        print(f"✅ 成功: {data.get('success')}")
        print(f"📝 笔记数量: {data.get('total_notes', 0)}")
        
        if data.get('error'):
            print(f"❌ 错误: {data['error']}")
        
        if data.get('notes'):
            print(f"\n📋 笔记详情:")
            for i, note in enumerate(data['notes'], 1):
                print(f"\n  [{i}] 笔记 {i}")
                print(f"      URL: {note.get('url', 'N/A')}")
                print(f"      图片: {len(note.get('images', []))} 张")
                print(f"      文本: {len(note.get('text', ''))} 字符")
                print(f"      评论: {len(note.get('comments', []))} 条")
                if note.get('saved_path'):
                    print(f"      保存路径: {note.get('saved_path')}")
        
        if data.get('storage_dir'):
            print(f"\n💾 数据已保存到: {data['storage_dir']}")
        
        print(f"\n💾 浏览器状态已保存到: {crawler.browser_data_dir}")
        print("   ✅ 下次运行将自动使用保存的登录状态！")
        
        print("\n" + "=" * 70)
        print("✨ 爬取完成！")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  爬取被用户中断")
    except Exception as e:
        print(f"\n❌ 爬取过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 再见！")

