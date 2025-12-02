"""
RedNote (小红书) Crawler Plugin Example

This example demonstrates how to use the RedNote crawler plugin
to crawl RedNote content with browser automation.
"""

import asyncio
import json
import os
from crawl4ai import CrawlerHub, LLMConfig
from crawl4ai.crawlers.rednote.crawler import RedNoteCrawler


async def example_1_direct_usage():
    """Example 1: Direct usage of RedNoteCrawler (without LLM)"""
    print("=" * 60)
    print("Example 1: Direct Usage (CSS Selectors)")
    print("=" * 60)
    
    # Create crawler instance without LLM
    crawler = RedNoteCrawler(
        feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url",
        use_llm_extraction=False,  # Use CSS selectors only
        storage_dir="./rednote_data"  # Custom storage directory
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
    
    if data.get('storage_dir'):
        print(f"\nData saved to: {data['storage_dir']}")


async def example_1b_with_llm():
    """Example 1b: Direct usage with LLM extraction"""
    print("=" * 60)
    print("Example 1b: Direct Usage with LLM Extraction")
    print("=" * 60)
    
    # Configure LLM (optional - only if you want intelligent extraction)
    llm_config = LLMConfig(
        provider="openai/gpt-4o-mini",  # or "ollama/llama2", etc.
        api_token=os.getenv("OPENAI_API_KEY")  # Set your API key
    )
    
    # Create crawler instance with LLM
    crawler = RedNoteCrawler(
        feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url",
        llm_config=llm_config,
        use_llm_extraction=True,  # Enable LLM extraction
        storage_dir="./rednote_data_llm"  # Custom storage directory
    )
    
    # Run crawler
    result = await crawler.run(
        search_keyword="牛奶",
        max_notes=5,
        headless=False,
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
            print(f"Title: {note.get('title', 'N/A')}")
            print(f"Author: {note.get('author', 'N/A')}")
            print(f"Images: {len(note.get('images', []))} images")
            print(f"Text length: {len(note.get('text', ''))} characters")
            print(f"Tags: {note.get('tags', [])}")
            print(f"Comments: {len(note.get('comments', []))} comments")
            print(f"Saved to: {note.get('saved_path', 'N/A')}")
    
    if data.get('error'):
        print(f"\nError: {data['error']}")
    
    if data.get('storage_dir'):
        print(f"\nData saved to: {data['storage_dir']}")


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


async def example_5_persistent_browser_state():
    """Example 5: Use persistent browser state to avoid re-login"""
    print("\n" + "=" * 60)
    print("Example 5: Persistent Browser State")
    print("=" * 60)
    print("\n💡 This example shows how to save browser state (cookies, login session)")
    print("   so you don't need to login every time you run the crawler.")
    print("\n📝 How it works:")
    print("   1. First run: Login manually in the browser window")
    print("   2. Browser state (cookies, localStorage) is saved to browser_data_dir")
    print("   3. Next run: Browser automatically loads saved state, no login needed!")
    print("=" * 60)
    
    # Option 1: Use default browser data directory (~/.crawl4ai/rednote_browser_profile)
    crawler = RedNoteCrawler(
        storage_dir="./rednote_data_persistent"
        # browser_data_dir is optional - defaults to ~/.crawl4ai/rednote_browser_profile
    )
    
    # Option 2: Use custom browser data directory
    # crawler = RedNoteCrawler(
    #     browser_data_dir="./my_rednote_browser_profile",  # Custom location
    #     storage_dir="./rednote_data_persistent"
    # )
    
    print(f"\n📁 Browser state directory: {crawler.browser_data_dir}")
    print(f"📁 Data storage directory: {crawler.storage_dir}")
    print("\n🚀 Starting crawler...")
    print("   (If this is the first run, you'll need to login manually)")
    print("   (On subsequent runs, login state will be automatically restored)")
    
    result = await crawler.run(
        search_keyword="牛奶",
        max_notes=5,
        headless=False,  # Non-headless to see the browser
        verbose=True
    )
    
    data = json.loads(result)
    print(f"\n✅ Success: {data.get('success')}")
    print(f"📊 Total notes crawled: {data.get('total_notes', 0)}")
    print(f"\n💾 Browser state saved to: {crawler.browser_data_dir}")
    print("   Next time you run this, login will be automatic!")


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
        print("\n💡 Tip: Browser state has been saved!")
        print(f"   Next time you run this, login will be automatic.")
        print(f"   Browser state location: {crawler.browser_data_dir}")
        
    except Exception as e:
        print(f"\n✗ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Uncomment the example you want to run:
    
    # Example 1: Basic usage without LLM (CSS selectors only)
    # asyncio.run(example_1_direct_usage())
    
    # Example 1b: Usage with LLM extraction (requires API key)
    # asyncio.run(example_1b_with_llm())
    
    # Example 2: Usage via CrawlerHub
    # asyncio.run(example_2_hub_usage())
    
    # Example 5: Persistent browser state (saves login, no re-login needed)
    # asyncio.run(example_5_persistent_browser_state())
    
    # Full crawl test
    asyncio.run(main())

