"""
Example: Using Crawl4AI Storage Backend with AsyncWebCrawler

This example demonstrates how to use the storage backend to persist
browser state across multiple crawler runs.
"""

import asyncio
from pathlib import Path
from crawl4ai import AsyncWebCrawler, BrowserConfig
from crawl4ai.storage import create_storage_backend


async def main():
    # Create storage backend (Minio example)
    storage = create_storage_backend(
        backend_type="minio",
        profile_name="example_profile",
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket_name="crawl4ai-browser-state",
        secure=False
    )
    
    # Try to load previous browser state
    print("Loading browser state from storage...")
    storage_state = await storage.load_storage_state()
    
    # Setup browser data directory
    browser_data_dir = Path("/tmp/crawl4ai_browser_data")
    browser_data_dir.mkdir(parents=True, exist_ok=True)
    
    # Try to load browser data directory
    if not await storage.load_browser_data_dir(target_dir=browser_data_dir):
        print("No previous browser data found, starting fresh...")
    
    # Configure browser with loaded state
    browser_config = BrowserConfig(
        headless=True,
        use_persistent_context=True,
        user_data_dir=str(browser_data_dir),
        storage_state=storage_state  # Use loaded state if available
    )
    
    # Run crawler
    async with AsyncWebCrawler(config=browser_config) as crawler:
        print("Crawling example.com...")
        result = await crawler.arun(url="https://example.com")
        
        if result.success:
            print(f"✓ Successfully crawled: {result.url}")
            print(f"  HTML length: {len(result.html)}")
            
            # Save browser state after crawling
            if crawler.crawler_strategy.default_context:
                context = crawler.crawler_strategy.default_context
                current_state = await context.storage_state()
                
                print("Saving browser state to storage...")
                await storage.save_browser_state(
                    storage_state=current_state,
                    browser_data_dir=browser_data_dir
                )
                print("✓ Browser state saved successfully")
        else:
            print(f"✗ Crawl failed: {result.error_message}")
    
    # List all profiles
    profiles = storage.list_profiles()
    print(f"\nAvailable profiles: {profiles}")


if __name__ == "__main__":
    asyncio.run(main())

