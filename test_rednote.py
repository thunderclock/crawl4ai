#!/usr/bin/env python3
"""
Quick test script for RedNote crawler plugin
"""

import asyncio
import json
import sys
from crawl4ai import CrawlerHub
from crawl4ai.crawlers.rednote.crawler import RedNoteCrawler


async def test_basic():
    """Test basic functionality"""
    print("=" * 60)
    print("RedNote Crawler Plugin - Basic Test")
    print("=" * 60)
    
    try:
        # Test 1: Import and instantiation
        print("\n[Test 1] Testing crawler import and instantiation...")
        crawler = RedNoteCrawler()
        print("✓ Crawler instantiated successfully")
        
        # Test 2: CrawlerHub registration
        print("\n[Test 2] Testing CrawlerHub registration...")
        RedNoteCrawlerClass = CrawlerHub.get("rednote")
        if RedNoteCrawlerClass:
            print("✓ RedNote crawler found in CrawlerHub")
            print(f"  Class: {RedNoteCrawlerClass.__name__}")
            print(f"  Meta: {RedNoteCrawlerClass.meta}")
        else:
            print("✗ RedNote crawler not found in CrawlerHub")
            return False
        
        # Test 3: Check meta information
        print("\n[Test 3] Testing meta information...")
        if hasattr(crawler, 'meta') or hasattr(RedNoteCrawler, 'meta'):
            meta = getattr(RedNoteCrawler, 'meta', {})
            print(f"✓ Meta information found:")
            print(f"  Version: {meta.get('version', 'N/A')}")
            print(f"  Description: {meta.get('description', 'N/A')}")
        
        print("\n" + "=" * 60)
        print("Basic tests passed! ✓")
        print("=" * 60)
        print("\nTo run a full crawl test, use:")
        print("  python examples/rednote_example.py")
        print("\nNote: Full crawl requires:")
        print("  - Browser window (non-headless mode)")
        print("  - Manual login to RedNote")
        print("  - Handling any captcha/verification")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_crawl():
    """Test actual crawling (requires manual interaction)"""
    print("\n" + "=" * 60)
    print("RedNote Crawler Plugin - Crawl Test")
    print("=" * 60)
    print("\n⚠️  This test will:")
    print("  1. Open a browser window")
    print("  2. Navigate to RedNote")
    print("  3. Wait for you to login (if needed)")
    print("  4. Search for '牛奶'")
    print("  5. Crawl 2 notes")
    print("\n💡 Browser State:")
    print("  - Browser state will be saved for future runs")
    print("  - Next time you run this, login will be automatic!")
    print("\nStarting in 5 seconds... (Press Ctrl+C to cancel)")
    
    try:
        await asyncio.sleep(5)
    except KeyboardInterrupt:
        print("\nTest cancelled by user")
        return False
    
    try:
        crawler = RedNoteCrawler()
        print(f"\n📁 Browser state directory: {crawler.browser_data_dir}")
        print(f"📁 Data storage directory: {crawler.storage_dir}")
        
        # Check if browser state already exists
        if crawler.browser_data_dir.exists() and any(crawler.browser_data_dir.iterdir()):
            print("✅ Found existing browser state - login should be automatic!")
        else:
            print("ℹ️  No existing browser state - you'll need to login this time")
        
        result = await crawler.run(
            search_keyword="牛奶",
            max_notes=2,
            headless=False,
            verbose=True
        )
        
        data = json.loads(result)
        print("\n" + "=" * 60)
        print("Crawl Results:")
        print("=" * 60)
        print(f"Success: {data.get('success')}")
        print(f"Total notes: {data.get('total_notes', 0)}")
        
        if data.get('error'):
            print(f"Error: {data['error']}")
        
        if data.get('notes'):
            for i, note in enumerate(data['notes'], 1):
                print(f"\n--- Note {i} ---")
                print(f"URL: {note.get('url', 'N/A')}")
                print(f"Images: {len(note.get('images', []))} images")
                print(f"Text: {len(note.get('text', ''))} chars")
                print(f"Comments: {len(note.get('comments', []))} comments")
        
        if data.get('success'):
            print(f"\n💾 Browser state saved to: {crawler.browser_data_dir}")
            print("   Next time you run this, login will be automatic!")
        
        return data.get('success', False)
        
    except Exception as e:
        print(f"\n✗ Error during crawl: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    if len(sys.argv) > 1 and sys.argv[1] == "--crawl":
        # Run full crawl test
        success = await test_crawl()
    else:
        # Run basic tests only
        success = await test_basic()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

