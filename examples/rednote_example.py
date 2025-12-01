"""
RedNote (小红书) Crawler Plugin Example

This example demonstrates how to use the RedNote crawler plugin
to crawl RedNote content with browser automation.
"""

import asyncio
import json
from crawl4ai import CrawlerHub
from crawl4ai.crawlers.rednote.crawler import RedNoteCrawler


async def example_1_direct_usage():
    """Example 1: Direct usage of RedNoteCrawler"""
    print("=" * 60)
    print("Example 1: Direct Usage")
    print("=" * 60)
    
    # Create crawler instance
    crawler = RedNoteCrawler(
        feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url"
    )
    
    # Run crawler
    result = await crawler.run(
        search_keyword="牛奶",
        max_notes=5,
        headless=False,  # Non-headless for manual login/verification
        verbose=True
    )
    
    # Parse and display results
    data = json.loads(result)
    print(f"\nSuccess: {data.get('success')}")
    print(f"Total notes crawled: {data.get('total_notes', 0)}")
    
    if data.get('notes'):
        for i, note in enumerate(data['notes'], 1):
            print(f"\n--- Note {i} ---")
            print(f"URL: {note.get('url')}")
            print(f"Images: {len(note.get('images', []))} images")
            print(f"Text length: {len(note.get('text', ''))} characters")
            print(f"Comments: {len(note.get('comments', []))} comments")
    
    if data.get('error'):
        print(f"\nError: {data['error']}")


async def example_2_hub_usage():
    """Example 2: Using CrawlerHub to get the crawler"""
    print("\n" + "=" * 60)
    print("Example 2: Using CrawlerHub")
    print("=" * 60)
    
    # Get crawler from hub
    RedNoteCrawlerClass = CrawlerHub.get("rednote")
    
    if RedNoteCrawlerClass:
        crawler = RedNoteCrawlerClass(
            feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url"
        )
        
        result = await crawler.run(
            search_keyword="咖啡",
            max_notes=3,
            headless=False
        )
        
        data = json.loads(result)
        print(f"\nCrawled {data.get('total_notes', 0)} notes")
    else:
        print("RedNote crawler not found in hub")


async def example_3_custom_keywords():
    """Example 3: Search with custom keywords"""
    print("\n" + "=" * 60)
    print("Example 3: Custom Keywords")
    print("=" * 60)
    
    keywords = ["美食", "旅行", "穿搭"]
    
    crawler = RedNoteCrawler()
    
    for keyword in keywords:
        print(f"\nSearching for: {keyword}")
        result = await crawler.run(
            search_keyword=keyword,
            max_notes=2,
            headless=False
        )
        
        data = json.loads(result)
        print(f"  Found {data.get('total_notes', 0)} notes for '{keyword}'")


async def example_4_save_results():
    """Example 4: Save results to file"""
    print("\n" + "=" * 60)
    print("Example 4: Save Results")
    print("=" * 60)
    
    crawler = RedNoteCrawler()
    
    result = await crawler.run(
        search_keyword="牛奶",
        max_notes=5,
        headless=False
    )
    
    # Save to file
    output_file = "rednote_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    
    print(f"Results saved to {output_file}")


async def main():
    """Run all examples"""
    print("RedNote Crawler Plugin Examples")
    print("=" * 60)
    print("\nNote: Make sure to:")
    print("1. Set your Feishu WebHook URL (optional)")
    print("2. Run in non-headless mode for first-time login")
    print("3. Complete any captcha/verification when prompted")
    print("\n")
    
    # Test basic functionality
    print("Starting basic test...")
    print("=" * 60)
    
    try:
        # Test 1: Check if crawler can be imported and instantiated
        print("\n[Test 1] Testing crawler import and instantiation...")
        crawler = RedNoteCrawler()
        print("✓ Crawler instantiated successfully")
        
        # Test 2: Check CrawlerHub registration
        print("\n[Test 2] Testing CrawlerHub registration...")
        RedNoteCrawlerClass = CrawlerHub.get("rednote")
        if RedNoteCrawlerClass:
            print("✓ RedNote crawler found in CrawlerHub")
        else:
            print("✗ RedNote crawler not found in CrawlerHub")
        
        # Test 3: Run a minimal crawl (with small max_notes for testing)
        print("\n[Test 3] Testing basic crawl functionality...")
        print("Note: This will open a browser window. Please:")
        print("  1. Login to RedNote if needed")
        print("  2. Complete any verification if prompted")
        print("  3. Wait for the crawl to complete")
        print("\nStarting crawl in 3 seconds...")
        await asyncio.sleep(3)
        
        result = await crawler.run(
            search_keyword="牛奶",
            max_notes=2,  # Small number for testing
            headless=False,  # Non-headless for manual interaction
            verbose=True
        )
        
        # Parse and display results
        data = json.loads(result)
        print("\n" + "=" * 60)
        print("Crawl Results:")
        print("=" * 60)
        print(f"Success: {data.get('success')}")
        print(f"Total notes crawled: {data.get('total_notes', 0)}")
        
        if data.get('error'):
            print(f"Error: {data['error']}")
        
        if data.get('notes'):
            for i, note in enumerate(data['notes'], 1):
                print(f"\n--- Note {i} ---")
                print(f"URL: {note.get('url', 'N/A')}")
                print(f"Images: {len(note.get('images', []))} images")
                print(f"Text length: {len(note.get('text', ''))} characters")
                print(f"Comments: {len(note.get('comments', []))} comments")
                
                # Show first few images if available
                images = note.get('images', [])
                if images:
                    print(f"  First image: {images[0][:80]}...")
                
                # Show text preview if available
                text = note.get('text', '')
                if text:
                    preview = text[:100] + "..." if len(text) > 100 else text
                    print(f"  Text preview: {preview}")
        
        print("\n" + "=" * 60)
        print("Test completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

