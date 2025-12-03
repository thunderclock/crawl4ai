"""
RedNote (小红书) Crawler Plugin for Crawl4AI

This plugin crawls RedNote content using Playwright browser automation.
Features:
- Browser-based interaction (clicks, navigation)
- Captcha/human verification detection with Feishu WebHook notification
- Mobile H5 verification support
- Content extraction: images, text, comments
"""

import json
import asyncio
import aiohttp
import random
import os
import tempfile
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from crawl4ai import BrowserConfig, AsyncWebCrawler, CrawlerRunConfig, CacheMode, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.hub import BaseCrawler
from crawl4ai.async_logger import AsyncLogger
from .minio_storage import MinioStorageManager


__meta__ = {
    "version": "1.0.0",
    "tested_on": ["xiaohongshu.com"],
    "rate_limit": "30 RPM",
    "description": "RedNote (小红书) crawler with browser automation, captcha detection, and content extraction",
    "schema": {
        "note": {
            "images": ["url"],
            "text": "string",
            "comments": ["text", "author", "likes"]
        }
    }
}


class RedNoteCrawler(BaseCrawler):
    """RedNote crawler with browser automation and verification handling"""
    
    def __init__(
        self, 
        feishu_webhook_url: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        use_llm_extraction: bool = True,
        storage_dir: Optional[str] = None,
        browser_data_dir: Optional[str] = None,
        # Minio configuration
        minio_endpoint: Optional[str] = None,
        minio_access_key: Optional[str] = None,
        minio_secret_key: Optional[str] = None,
        minio_bucket: str = "rednote-browser-state",
        minio_secure: bool = True,
        minio_region: Optional[str] = None,
        minio_profile_name: str = "default"
    ):
        """
        Initialize RedNote crawler
        
        Args:
            feishu_webhook_url: Feishu WebHook URL for captcha notifications
            llm_config: LLM configuration for intelligent extraction (optional)
            use_llm_extraction: Whether to use LLM for extraction (default: True)
            storage_dir: Directory to store crawled data (default: temp directory)
            browser_data_dir: Directory to store browser state (cookies, localStorage, etc.)
                             If None, uses ~/.crawl4ai/rednote_browser_profile
            minio_endpoint: Minio server endpoint (e.g., 'localhost:9000')
            minio_access_key: Minio access key
            minio_secret_key: Minio secret key
            minio_bucket: Minio bucket name (default: 'rednote-browser-state')
            minio_secure: Use HTTPS for Minio (default: True)
            minio_region: Minio region name (optional)
            minio_profile_name: Profile name for browser state in Minio (default: 'default')
        """
        super().__init__()
        self.feishu_webhook_url = feishu_webhook_url
        self.base_url = "https://www.xiaohongshu.com"
        self.search_url = f"{self.base_url}/search_result"
        self.crawler: Optional[AsyncWebCrawler] = None
        self.page: Optional[Page] = None
        self.llm_config = llm_config
        self.use_llm_extraction = use_llm_extraction
        
        # Setup browser data directory for persistent context (saves login state)
        if browser_data_dir:
            self.browser_data_dir = Path(browser_data_dir)
        else:
            # Use default directory in user's home
            home_dir = Path.home()
            self.browser_data_dir = home_dir / ".crawl4ai" / "rednote_browser_profile"
        
        self.browser_data_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Browser state will be saved to: {self.browser_data_dir}")
        
        # Setup storage directory
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            # Use temp directory with timestamp
            temp_base = Path(tempfile.gettempdir()) / "rednote_crawler"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.storage_dir = temp_base / timestamp
        
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Data will be stored in: {self.storage_dir}")
        
        # Setup Minio storage manager if configured
        self.minio_storage: Optional[MinioStorageManager] = None
        self.minio_profile_name = minio_profile_name
        if minio_endpoint and minio_access_key and minio_secret_key:
            try:
                self.minio_storage = MinioStorageManager(
                    endpoint=minio_endpoint,
                    access_key=minio_access_key,
                    secret_key=minio_secret_key,
                    bucket_name=minio_bucket,
                    secure=minio_secure,
                    region=minio_region,
                    logger=self.logger
                )
                self.logger.info(f"Minio storage enabled: {minio_endpoint}/{minio_bucket}")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Minio storage: {str(e)}")
                self.minio_storage = None
    
    async def _save_browser_state_to_minio(self):
        """Save browser state to Minio if configured"""
        if not self.minio_storage or not self.crawler:
            return
        
        try:
            # Get browser context
            strategy = self.crawler.crawler_strategy
            if hasattr(strategy, 'default_context') and strategy.default_context:
                context = strategy.default_context
                
                # Export storage state
                storage_state = await context.storage_state()
                
                # Save to Minio
                await self.minio_storage.save_browser_state(
                    storage_state=storage_state,
                    browser_data_dir=self.browser_data_dir,
                    profile_name=self.minio_profile_name
                )
                
                self.logger.info("Browser state saved to Minio successfully")
        except Exception as e:
            self.logger.warning(f"Failed to save browser state to Minio: {str(e)}")
    
    async def _load_browser_state_from_minio(self) -> bool:
        """Load browser state from Minio if configured and available"""
        if not self.minio_storage:
            return False
        
        try:
            # Try to load browser data directory first
            loaded = await self.minio_storage.load_browser_data_dir(
                target_dir=self.browser_data_dir,
                profile_name=self.minio_profile_name,
                use_latest=True
            )
            
            if loaded:
                self.logger.info("Browser data directory loaded from Minio")
            
            # Try to load storage state
            storage_state = await self.minio_storage.load_storage_state(
                profile_name=self.minio_profile_name
            )
            
            if storage_state:
                self.logger.info("Storage state loaded from Minio")
                return True
            
            return loaded
        except Exception as e:
            self.logger.warning(f"Failed to load browser state from Minio: {str(e)}")
            return False
    
    async def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Add random delay between 1-3 seconds (or custom range) to simulate human behavior"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
        
    async def _get_page(self, config: Optional[CrawlerRunConfig] = None) -> Page:
        """Get the Playwright page object from the crawler"""
        if not self.crawler:
            raise RuntimeError("Crawler not initialized. Call run() first.")
        
        # Access the page through the crawler's strategy
        strategy = self.crawler.crawler_strategy
        if hasattr(strategy, 'browser_manager'):
            crawler_config = config or CrawlerRunConfig(session_id="rednote_session")
            page, context = await strategy.browser_manager.get_page(
                crawlerRunConfig=crawler_config
            )
            return page
        else:
            raise RuntimeError("Cannot access page object from crawler")
    
    async def _send_feishu_notification(
        self, 
        title: str, 
        content: str, 
        verification_url: Optional[str] = None
    ):
        """Send notification to Feishu via WebHook"""
        if not self.feishu_webhook_url:
            self.logger.warning("Feishu WebHook URL not configured, skipping notification")
            return
        
        try:
            message = {
                "msg_type": "interactive",
                "card": {
                    "config": {
                        "wide_screen_mode": True
                    },
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": title
                        },
                        "template": "red" if "验证" in title or "验证码" in title else "blue"
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": content
                            }
                        }
                    ]
                }
            }
            
            if verification_url:
                message["card"]["elements"].append({
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "打开验证页面"
                            },
                            "type": "default",
                            "url": verification_url
                        }
                    ]
                })
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.feishu_webhook_url,
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.logger.info("Feishu notification sent successfully")
                    else:
                        self.logger.warning(f"Feishu notification failed: {response.status}")
        except Exception as e:
            self.logger.error(f"Failed to send Feishu notification: {str(e)}")
    
    async def _detect_captcha(self, page: Page) -> bool:
        """Detect if there's a captcha or verification on the page"""
        try:
            # Common captcha/verification selectors for RedNote
            captcha_selectors = [
                'iframe[src*="captcha"]',
                'iframe[src*="verify"]',
                '.captcha',
                '.verification',
                '[class*="captcha"]',
                '[class*="verify"]',
                '[id*="captcha"]',
                '[id*="verify"]',
                '//text()[contains(., "验证码")]',
                '//text()[contains(., "人机验证")]',
                '//text()[contains(., "安全验证")]',
            ]
            
            for selector in captcha_selectors:
                try:
                    if selector.startswith('//'):
                        # XPath selector
                        element = await page.query_selector(f'xpath={selector}')
                    else:
                        element = await page.query_selector(selector)
                    
                    if element:
                        # Check if element is visible
                        is_visible = await element.is_visible()
                        if is_visible:
                            return True
                except Exception:
                    continue
            
            # Check page content for verification keywords
            content = await page.content()
            verification_keywords = ["验证码", "人机验证", "安全验证", "滑动验证", "点击验证"]
            if any(keyword in content for keyword in verification_keywords):
                return True
                
            return False
        except Exception as e:
            self.logger.warning(f"Error detecting captcha: {str(e)}")
            return False
    
    async def _handle_verification(self, page: Page):
        """Handle verification by sending notification to Feishu"""
        current_url = page.url
        screenshot_path = None
        
        try:
            # Take screenshot for reference
            screenshot_path = f"/tmp/rednote_verification_{asyncio.get_event_loop().time()}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            pass
        
        # Generate mobile H5 verification URL (if needed)
        # RedNote mobile URL format
        mobile_url = current_url.replace("www.xiaohongshu.com", "m.xiaohongshu.com")
        
        # Send notification to Feishu
        content = f"""
**检测到验证码/人机验证**

- 当前页面: {current_url}
- 移动端验证链接: {mobile_url}

请在移动端H5页面完成验证后，爬虫将继续运行。

**操作步骤:**
1. 在手机上打开移动端验证链接
2. 完成滑动验证或其他验证操作
3. 验证完成后，爬虫将自动继续
"""
        
        await self._send_feishu_notification(
            title="⚠️ RedNote验证码检测",
            content=content,
            verification_url=mobile_url
        )
        
        # Wait for user to complete verification (with timeout)
        self.logger.info("Waiting for verification to complete...")
        max_wait_time = 300  # 5 minutes
        wait_interval = 5  # Check every 5 seconds
        
        for _ in range(max_wait_time // wait_interval):
            await asyncio.sleep(wait_interval)
            if not await self._detect_captcha(page):
                self.logger.info("Verification appears to be completed")
                return
        
        self.logger.warning("Verification timeout reached")
    
    async def _wait_for_element(
        self, 
        page: Page, 
        selector: str, 
        timeout: int = 30000,
        state: str = "visible"
    ) -> bool:
        """Wait for an element to appear on the page"""
        try:
            await page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except PlaywrightTimeoutError:
            return False
    
    async def _click_element(
        self, 
        page: Page, 
        selector: str, 
        timeout: int = 10000
    ) -> bool:
        """Click an element on the page"""
        try:
            element = await page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                await element.click()
                await asyncio.sleep(1)  # Wait for page to react
                return True
        except Exception as e:
            self.logger.warning(f"Failed to click element {selector}: {str(e)}")
        return False
    
    async def _login_if_needed(self, page: Page):
        """Check if login is needed and wait for user to login"""
        try:
            # Check for login indicators
            login_selectors = [
                'a[href*="login"]',
                'button:has-text("登录")',
                '.login',
                '[class*="login"]'
            ]
            
            needs_login = False
            for selector in login_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        needs_login = True
                        break
                except Exception:
                    continue
            
            if needs_login:
                self.logger.info("Login required. Waiting for user to login...")
                await self._send_feishu_notification(
                    title="🔐 RedNote登录提醒",
                    content="检测到需要登录，请在浏览器中完成登录操作。"
                )
                
                # Wait for login to complete (check if login elements disappear)
                max_wait = 300  # 5 minutes
                for _ in range(max_wait // 5):
                    await asyncio.sleep(5)
                    still_needs_login = False
                    for selector in login_selectors:
                        try:
                            element = await page.query_selector(selector)
                            if element and await element.is_visible():
                                still_needs_login = True
                                break
                        except Exception:
                            pass
                    
                    if not still_needs_login:
                        self.logger.info("Login appears to be completed")
                        return
                
                self.logger.warning("Login timeout reached")
        except Exception as e:
            self.logger.warning(f"Error checking login status: {str(e)}")
    
    async def _search_content(self, page: Page, keyword: str = "牛奶"):
        """Search for content on RedNote using search box"""
        try:
            self.logger.info(f"Searching for: {keyword}")
            
            # Navigate to RedNote homepage first (if not already there)
            if "xiaohongshu.com" not in page.url or "/search" in page.url:
                self.logger.info("Navigating to RedNote homepage...")
                await page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for search box to appear instead of waiting for network idle
                self.logger.info("Waiting for search box to appear...")
                search_box_selectors = [
                    'input[placeholder*="搜索"]',
                    'input[placeholder*="搜索笔记"]',
                    'input[type="search"]',
                    'input[class*="search"]',
                    '.search-input input',
                    '[class*="search"] input',
                    'input[aria-label*="搜索"]',
                    'input[name*="search"]',
                    'input[id*="search"]'
                ]
                
                search_box_found = False
                for selector in search_box_selectors:
                    try:
                        await page.wait_for_selector(selector, state="visible", timeout=30000)
                        self.logger.info(f"Search box appeared: {selector}")
                        search_box_found = True
                        break
                    except Exception:
                        continue
                
                if not search_box_found:
                    self.logger.warning("Search box not found immediately, continuing anyway...")
                    await asyncio.sleep(2)
            
            # Check for captcha
            if await self._detect_captcha(page):
                await self._handle_verification(page)
            
            # Find search box - try multiple selectors
            search_box_selectors = [
                'input[placeholder*="搜索"]',
                'input[placeholder*="搜索笔记"]',
                'input[type="search"]',
                'input[class*="search"]',
                '.search-input input',
                '[class*="search"] input',
                'input[aria-label*="搜索"]',
                'input[name*="search"]',
                'input[id*="search"]'
            ]
            
            search_box = None
            for selector in search_box_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            search_box = element
                            self.logger.info(f"Found search box using selector: {selector}")
                            break
                except Exception:
                    continue
            
            if not search_box:
                # Try to find search box by clicking on search icon/button first
                self.logger.info("Search box not found directly, trying to click search icon...")
                search_icon_selectors = [
                    '.search-icon',
                    '[class*="search-icon"]',
                    'button[aria-label*="搜索"]',
                    'button[class*="search"]',
                    '.search-button',
                    '[class*="search-button"]'
                ]
                
                for icon_selector in search_icon_selectors:
                    try:
                        icon = await page.query_selector(icon_selector)
                        if icon and await icon.is_visible():
                            await self._random_delay(1, 3)
                            await icon.click()
                            await asyncio.sleep(1)
                            # Try to find search box again
                            for selector in search_box_selectors:
                                try:
                                    element = await page.query_selector(selector)
                                    if element:
                                        is_visible = await element.is_visible()
                                        if is_visible:
                                            search_box = element
                                            self.logger.info(f"Found search box after clicking icon: {selector}")
                                            break
                                except Exception:
                                    continue
                            if search_box:
                                break
                    except Exception:
                        continue
            
            if not search_box:
                self.logger.error("Could not find search box")
                return False
            
            # Click on search box to focus
            await self._random_delay(1, 3)
            await search_box.click()
            await asyncio.sleep(0.5)
            
            # Clear any existing text
            await search_box.fill("")
            await asyncio.sleep(0.3)
            
            # Type the search keyword
            self.logger.info(f"Typing search keyword: {keyword}")
            await search_box.type(keyword, delay=100)  # Type with delay to simulate human typing
            await asyncio.sleep(0.5)
            
            # Submit search - try multiple methods
            search_submitted = False
            
            # Method 1: Press Enter key
            try:
                await search_box.press("Enter")
                search_submitted = True
                self.logger.info("Submitted search by pressing Enter")
            except Exception as e:
                self.logger.warning(f"Failed to press Enter: {str(e)}")
            
            # Method 2: If Enter didn't work, try to find and click search button
            if not search_submitted:
                search_button_selectors = [
                    'button[type="submit"]',
                    'button:has-text("搜索")',
                    '.search-submit',
                    '[class*="search-submit"]',
                    'button[aria-label*="搜索"]'
                ]
                
                for button_selector in search_button_selectors:
                    try:
                        button = await page.query_selector(button_selector)
                        if button and await button.is_visible():
                            await self._random_delay(1, 3)
                            await button.click()
                            search_submitted = True
                            self.logger.info(f"Submitted search by clicking button: {button_selector}")
                            break
                    except Exception:
                        continue
            
            if not search_submitted:
                self.logger.warning("Could not submit search, but continuing...")
            
            # Wait for page to navigate/load search results
            self.logger.info("Waiting for search results to load...")
            await asyncio.sleep(3)
            
            # Check if URL changed (indicating navigation to search results)
            current_url = page.url
            if "/search" in current_url or "keyword" in current_url.lower():
                self.logger.info(f"Navigated to search results page: {current_url}")
            else:
                self.logger.info("URL may not have changed, but continuing...")
            
            # Check for captcha after search
            if await self._detect_captcha(page):
                await self._handle_verification(page)
            
            # Wait for search results to load
            # RedNote search result selectors (these may need adjustment based on actual page structure)
            result_selectors = [
                '.note-item',
                '.feed-item',
                '[class*="note"]',
                '[class*="feed"]',
                '.feeds-page',
                '.search-result',
                '[class*="search-result"]'
            ]
            
            # Wait a bit more for results to render
            await asyncio.sleep(2)
            
            # Scroll a bit to trigger lazy loading
            await page.evaluate("window.scrollTo(0, 300)")
            await asyncio.sleep(1)
            
            for selector in result_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        self.logger.info(f"Search results loaded (found {len(elements)} elements with selector: {selector})")
                        return True
                except Exception:
                    continue
            
            # Even if no specific selector found, check if page has content
            content = await page.content()
            if len(content) > 10000:  # Page has substantial content
                self.logger.info("Search results page loaded (detected by content size)")
                return True
            
            self.logger.warning("Search results may not have loaded properly, but continuing...")
            return True  # Return True anyway to continue
            
        except Exception as e:
            self.logger.error(f"Error during search: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _extract_note_images(self, page: Page) -> List[str]:
        """Extract image URLs from a note page"""
        images = []
        try:
            # Common image selectors for RedNote notes
            image_selectors = [
                'img[src*="sns-img"]',
                'img[src*="xiaohongshu"]',
                '.note-image img',
                '.image img',
                '[class*="image"] img',
                'img[alt*="图片"]'
            ]
            
            for selector in image_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        src = await element.get_attribute('src')
                        if src and src not in images:
                            # Handle relative URLs
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src.startswith('/'):
                                src = self.base_url + src
                            images.append(src)
                except Exception:
                    continue
            
            # Also try to extract from background-image CSS
            try:
                elements_with_bg = await page.query_selector_all('[style*="background-image"]')
                for element in elements_with_bg:
                    style = await element.get_attribute('style')
                    if style and 'url(' in style:
                        import re
                        urls = re.findall(r'url\(["\']?([^"\']+)["\']?\)', style)
                        for url in urls:
                            if url not in images:
                                if url.startswith('//'):
                                    url = 'https:' + url
                                elif url.startswith('/'):
                                    url = self.base_url + url
                                images.append(url)
            except Exception:
                pass
            
            return images
        except Exception as e:
            self.logger.warning(f"Error extracting images: {str(e)}")
            return images
    
    async def _extract_note_text(self, page: Page) -> str:
        """Extract text content from a note page"""
        try:
            # Common text selectors for RedNote notes
            text_selectors = [
                '.note-content',
                '.content',
                '.desc',
                '[class*="content"]',
                '[class*="desc"]',
                '[class*="text"]'
            ]
            
            text_parts = []
            for selector in text_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        text = await element.inner_text()
                        if text and text.strip():
                            text_parts.append(text.strip())
                except Exception:
                    continue
            
            # If no specific content found, try to get main text
            if not text_parts:
                try:
                    main_content = await page.query_selector('main, article, .main-content')
                    if main_content:
                        text = await main_content.inner_text()
                        if text:
                            text_parts.append(text.strip())
                except Exception:
                    pass
            
            return '\n'.join(text_parts) if text_parts else ""
        except Exception as e:
            self.logger.warning(f"Error extracting text: {str(e)}")
            return ""
    
    async def _extract_comments(self, page: Page) -> List[Dict[str, Any]]:
        """Extract comments from a note page"""
        comments = []
        try:
            # Scroll to load comments
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            # Common comment selectors for RedNote
            comment_selectors = [
                '.comment-item',
                '.comment',
                '[class*="comment"]',
                '.reply-item'
            ]
            
            for selector in comment_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        comment_data = {}
                        
                        # Extract comment text
                        text_elem = await element.query_selector('.comment-text, .text, [class*="text"]')
                        if text_elem:
                            comment_data['text'] = await text_elem.inner_text()
                        
                        # Extract author
                        author_elem = await element.query_selector('.author, .username, [class*="author"], [class*="user"]')
                        if author_elem:
                            comment_data['author'] = await author_elem.inner_text()
                        
                        # Extract likes
                        likes_elem = await element.query_selector('.likes, .like-count, [class*="like"]')
                        if likes_elem:
                            likes_text = await likes_elem.inner_text()
                            try:
                                comment_data['likes'] = int(''.join(filter(str.isdigit, likes_text)))
                            except:
                                comment_data['likes'] = 0
                        
                        if comment_data.get('text'):
                            comments.append(comment_data)
                except Exception:
                    continue
            
            return comments
        except Exception as e:
            self.logger.warning(f"Error extracting comments: {str(e)}")
            return comments
    
    async def _click_note(self, page: Page, note_selector: str) -> bool:
        """Click on a note to open it"""
        try:
            element = await page.query_selector(note_selector)
            if element:
                # Scroll element into view
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                
                # Click the element
                await element.click()
                await asyncio.sleep(2)  # Wait for note page to load
                
                # Check for captcha
                if await self._detect_captcha(page):
                    await self._handle_verification(page)
                
                return True
        except Exception as e:
            self.logger.warning(f"Failed to click note: {str(e)}")
        return False
    
    async def _apply_filter_sort(self, page: Page):
        """Click filter button and select '最多点赞' (Most Likes)"""
        try:
            self.logger.info("Looking for filter button...")
            
            # Find filter button - try multiple selectors
            filter_selectors = [
                'button:has-text("筛选")',
                'button[aria-label*="筛选"]',
                '.filter-button',
                '[class*="filter"]',
                'button:contains("筛选")',
                '//button[contains(text(), "筛选")]'
            ]
            
            filter_button = None
            for selector in filter_selectors:
                try:
                    if selector.startswith('//'):
                        # XPath selector
                        element = await page.query_selector(f'xpath={selector}')
                    else:
                        element = await page.query_selector(selector)
                    
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            filter_button = element
                            self.logger.info(f"Found filter button using selector: {selector}")
                            break
                except Exception:
                    continue
            
            if not filter_button:
                self.logger.warning("Could not find filter button, skipping filter step")
                return False
            
            # Click filter button
            await self._random_delay(1, 3)
            await filter_button.click()
            await asyncio.sleep(1)
            self.logger.info("Clicked filter button")
            
            # Wait for filter menu to appear
            await asyncio.sleep(1)
            
            # Find and click "最多点赞" option
            self.logger.info("Looking for '最多点赞' option...")
            most_likes_selectors = [
                'button:has-text("最多点赞")',
                'div:has-text("最多点赞")',
                '[class*="最多点赞"]',
                '//div[contains(text(), "最多点赞")]',
                '//button[contains(text(), "最多点赞")]',
                '.sort-option:has-text("最多点赞")',
                '[data-value*="like"]'
            ]
            
            most_likes_option = None
            for selector in most_likes_selectors:
                try:
                    if selector.startswith('//'):
                        element = await page.query_selector(f'xpath={selector}')
                    else:
                        element = await page.query_selector(selector)
                    
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            most_likes_option = element
                            self.logger.info(f"Found '最多点赞' option using selector: {selector}")
                            break
                except Exception:
                    continue
            
            if not most_likes_option:
                self.logger.warning("Could not find '最多点赞' option")
                return False
            
            # Click "最多点赞" option
            await self._random_delay(1, 3)
            await most_likes_option.click()
            await asyncio.sleep(1)
            self.logger.info("Clicked '最多点赞' option")
            
            # Wait for page to refresh/update
            self.logger.info("Waiting for page to refresh after filter...")
            await asyncio.sleep(3)
            
            # Scroll to top to ensure we see the first row
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error applying filter: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _get_rednote_schema(self) -> Dict[str, Any]:
        """Get JSON schema for RedNote note extraction"""
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "笔记标题或主题"
                },
                "text": {
                    "type": "string",
                    "description": "笔记的完整文本内容"
                },
                "images": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "图片URL"
                    },
                    "description": "笔记中的所有图片URL列表"
                },
                "tags": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "笔记中的标签或话题"
                },
                "comments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "评论内容"
                            },
                            "author": {
                                "type": "string",
                                "description": "评论作者用户名"
                            },
                            "likes": {
                                "type": "integer",
                                "description": "评论点赞数"
                            },
                            "time": {
                                "type": "string",
                                "description": "评论时间"
                            }
                        },
                        "required": ["text"]
                    },
                    "description": "评论列表"
                },
                "author": {
                    "type": "string",
                    "description": "笔记作者用户名"
                },
                "likes": {
                    "type": "integer",
                    "description": "笔记点赞数"
                },
                "collections": {
                    "type": "integer",
                    "description": "笔记收藏数"
                }
            },
            "required": ["text", "images"]
        }
    
    async def _extract_with_llm(self, page: Page, html_content: str) -> Optional[Dict[str, Any]]:
        """Extract note data using LLM if configured"""
        if not self.use_llm_extraction or not self.llm_config:
            return None
        
        try:
            self.logger.info("Using LLM for intelligent extraction...")
            
            # Create LLM extraction strategy
            llm_strategy = LLMExtractionStrategy(
                llm_config=self.llm_config,
                schema=self._get_rednote_schema(),
                extraction_type="schema",
                instruction="""从RedNote（小红书）笔记页面中提取结构化数据。
请仔细分析HTML内容，提取以下信息：
1. 笔记的标题或主题
2. 笔记的完整文本内容（去除HTML标签，保留纯文本）
3. 所有图片的URL（排除头像、图标等小图片）
4. 笔记中的标签或话题
5. 所有评论信息（包括评论内容、作者、点赞数、时间）
6. 笔记作者用户名
7. 笔记的点赞数和收藏数

请确保提取的数据准确完整，图片URL必须是完整的可访问URL。""",
                apply_chunking=False,
                force_json_response=True,
                verbose=self.logger.verbose if hasattr(self.logger, 'verbose') else False
            )
            
            # Extract using LLM
            extracted = llm_strategy.extract(
                url=page.url,
                ix=0,
                html=html_content
            )
            
            if extracted and len(extracted) > 0:
                # LLM returns a list, get the first result
                result = extracted[0] if isinstance(extracted, list) else extracted
                if isinstance(result, dict):
                    self.logger.info("LLM extraction successful")
                    return result
            
        except Exception as e:
            self.logger.warning(f"LLM extraction failed, falling back to CSS selectors: {str(e)}")
        
        return None
    
    async def _extract_note_data_from_popup(self, page: Page) -> Dict[str, Any]:
        """Extract data from popup/modal dialog (not from full page)"""
        note_data = {
            "url": page.url,
            "images": [],
            "text": "",
            "comments": [],
            "title": "",
            "tags": [],
            "author": "",
            "likes": 0,
            "collections": 0
        }
        
        try:
            # Wait for popup to appear
            await asyncio.sleep(1)
            
            # Get page HTML for LLM extraction
            html_content = await page.content()
            
            # Try LLM extraction first if enabled
            if self.use_llm_extraction and self.llm_config:
                llm_result = await self._extract_with_llm(page, html_content)
                if llm_result:
                    # Merge LLM results with note_data
                    note_data.update({
                        "title": llm_result.get("title", ""),
                        "text": llm_result.get("text", ""),
                        "images": llm_result.get("images", []),
                        "tags": llm_result.get("tags", []),
                        "comments": llm_result.get("comments", []),
                        "author": llm_result.get("author", ""),
                        "likes": llm_result.get("likes", 0),
                        "collections": llm_result.get("collections", 0)
                    })
                    # If LLM extraction was successful, return early
                    if note_data.get("text") or note_data.get("images"):
                        return note_data
            
            # Fallback to CSS selector extraction if LLM failed or not enabled
            # Find popup/modal container
            popup_selectors = [
                '.modal',
                '.popup',
                '.dialog',
                '[class*="modal"]',
                '[class*="popup"]',
                '[class*="dialog"]',
                '[class*="detail"]',
                '.note-detail',
                '[class*="note-detail"]'
            ]
            
            popup_container = None
            for selector in popup_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            popup_container = element
                            self.logger.info(f"Found popup container using selector: {selector}")
                            break
                except Exception:
                    continue
            
            # If popup container found, extract from it, otherwise extract from page
            target = popup_container if popup_container else page
            
            # Extract images from popup
            try:
                if popup_container:
                    image_elements = await popup_container.query_selector_all('img')
                else:
                    image_elements = await page.query_selector_all('img')
                
                for img in image_elements:
                    src = await img.get_attribute('src')
                    if src and src not in note_data["images"]:
                        # Filter out small icons and avatars
                        if any(x in src.lower() for x in ['avatar', 'icon', 'logo', 'default']):
                            continue
                        # Handle relative URLs
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = self.base_url + src
                        if 'sns-img' in src or 'xiaohongshu' in src:
                            note_data["images"].append(src)
            except Exception as e:
                self.logger.warning(f"Error extracting images from popup: {str(e)}")
            
            # Extract text from popup
            try:
                if popup_container:
                    text_elements = await popup_container.query_selector_all(
                        '.note-content, .content, .desc, [class*="content"], [class*="desc"], [class*="text"]'
                    )
                else:
                    text_elements = await page.query_selector_all(
                        '.note-content, .content, .desc, [class*="content"], [class*="desc"], [class*="text"]'
                    )
                
                text_parts = []
                for elem in text_elements:
                    text = await elem.inner_text()
                    if text and text.strip() and len(text.strip()) > 10:  # Filter out very short text
                        text_parts.append(text.strip())
                
                if text_parts:
                    note_data["text"] = '\n'.join(text_parts)
            except Exception as e:
                self.logger.warning(f"Error extracting text from popup: {str(e)}")
            
            # Extract comments from popup
            try:
                if popup_container:
                    comment_elements = await popup_container.query_selector_all(
                        '.comment-item, .comment, [class*="comment"], .reply-item'
                    )
                else:
                    comment_elements = await page.query_selector_all(
                        '.comment-item, .comment, [class*="comment"], .reply-item'
                    )
                
                for element in comment_elements:
                    comment_data = {}
                    
                    # Extract comment text
                    text_elem = await element.query_selector('.comment-text, .text, [class*="text"]')
                    if text_elem:
                        comment_data['text'] = await text_elem.inner_text()
                    
                    # Extract author
                    author_elem = await element.query_selector('.author, .username, [class*="author"], [class*="user"]')
                    if author_elem:
                        comment_data['author'] = await author_elem.inner_text()
                    
                    # Extract likes
                    likes_elem = await element.query_selector('.likes, .like-count, [class*="like"]')
                    if likes_elem:
                        likes_text = await likes_elem.inner_text()
                        try:
                            comment_data['likes'] = int(''.join(filter(str.isdigit, likes_text)))
                        except:
                            comment_data['likes'] = 0
                    
                    if comment_data.get('text'):
                        note_data["comments"].append(comment_data)
            except Exception as e:
                self.logger.warning(f"Error extracting comments from popup: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Error extracting note data from popup: {str(e)}")
        
        return note_data
    
    async def _download_image(self, image_url: str, save_path: Path) -> Optional[str]:
        """Download an image from URL and save to local path"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        # Get file extension from content-type or URL
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'jpeg' in content_type or 'jpg' in content_type:
                            ext = '.jpg'
                        elif 'png' in content_type:
                            ext = '.png'
                        elif 'webp' in content_type:
                            ext = '.webp'
                        elif 'gif' in content_type:
                            ext = '.gif'
                        else:
                            # Try to get extension from URL
                            url_ext = Path(image_url.split('?')[0]).suffix.lower()
                            if url_ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                                ext = url_ext
                            else:
                                ext = '.jpg'  # Default to jpg
                        
                        # Update save_path with correct extension if needed
                        if save_path.suffix.lower() != ext:
                            save_path = save_path.with_suffix(ext)
                        
                        # Save image
                        image_data = await response.read()
                        with open(save_path, 'wb') as f:
                            f.write(image_data)
                        
                        self.logger.info(f"Downloaded image: {save_path.name} ({len(image_data)} bytes)")
                        return str(save_path)
                    else:
                        self.logger.warning(f"Failed to download image {image_url}: HTTP {response.status}")
                        return None
        except Exception as e:
            self.logger.warning(f"Error downloading image {image_url}: {str(e)}")
            return None
    
    async def _save_note_data(self, note_data: Dict[str, Any], note_index: int):
        """Save note data to local storage directory and download images"""
        try:
            # Create filename with timestamp and index
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"note_{note_index:02d}_{timestamp}.json"
            filepath = self.storage_dir / filename
            
            # Create images directory for this note
            images_dir = self.storage_dir / f"note_{note_index:02d}_{timestamp}_images"
            images_dir.mkdir(exist_ok=True)
            
            # Download and save images
            downloaded_images = []
            if note_data.get("images"):
                self.logger.info(f"Downloading {len(note_data['images'])} images for note {note_index}...")
                for img_idx, image_url in enumerate(note_data["images"], 1):
                    try:
                        # Create image filename (extension will be determined during download)
                        image_filename_base = f"image_{img_idx:02d}"
                        image_path = images_dir / image_filename_base
                        
                        # Download image (extension will be added based on content type)
                        downloaded_path = await self._download_image(image_url, image_path)
                        if downloaded_path:
                            downloaded_path_obj = Path(downloaded_path)
                            downloaded_images.append({
                                "original_url": image_url,
                                "local_path": str(downloaded_path_obj.relative_to(self.storage_dir)),
                                "filename": downloaded_path_obj.name,
                                "index": img_idx
                            })
                    except Exception as e:
                        self.logger.warning(f"Error downloading image {img_idx}: {str(e)}")
                        continue
                
                # Update note_data with local image paths
                note_data["downloaded_images"] = downloaded_images
                note_data["images_dir"] = str(images_dir.relative_to(self.storage_dir))
            
            # Save as JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(note_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Saved note data to: {filepath}")
            if downloaded_images:
                self.logger.info(f"Downloaded {len(downloaded_images)} images to: {images_dir}")
            
            # Also save images list separately if needed
            if note_data.get("images"):
                images_file = self.storage_dir / f"note_{note_index:02d}_images.json"
                with open(images_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "url": note_data.get("url"), 
                        "images": note_data["images"],
                        "downloaded_images": downloaded_images
                    }, f, ensure_ascii=False, indent=2)
            
            return str(filepath)
        except Exception as e:
            self.logger.error(f"Error saving note data: {str(e)}")
            return None
    
    async def _close_popup(self, page: Page):
        """Close popup by clicking outside of it"""
        try:
            # First, try pressing Escape key (most reliable)
            try:
                await page.keyboard.press('Escape')
                await asyncio.sleep(0.5)
                self.logger.info("Closed popup by pressing Escape")
            except Exception:
                pass
            
            # Try clicking on the mask/overlay elements (including note-detail-mask)
            mask_selectors = [
                '[class*="note-detail-mask"]',
                '[class*="mask"]',
                '.modal-backdrop',
                '.overlay',
                '.backdrop',
                '[class*="backdrop"]',
                '[class*="overlay"]',
                '[class*="modal"]'
            ]
            
            for selector in mask_selectors:
                try:
                    mask = await page.query_selector(selector)
                    if mask:
                        is_visible = await mask.is_visible()
                        if is_visible:
                            # Try clicking the mask directly
                            try:
                                await mask.click(timeout=2000)
                                await asyncio.sleep(0.5)
                                self.logger.info(f"Closed popup by clicking mask: {selector}")
                            except Exception:
                                # If click fails, try clicking at center of mask
                                try:
                                    box = await mask.bounding_box()
                                    if box:
                                        await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                                        await asyncio.sleep(0.5)
                                        self.logger.info(f"Closed popup by clicking mask center: {selector}")
                                except Exception:
                                    pass
                except Exception:
                    continue
            
            # Wait for mask to disappear
            await asyncio.sleep(1)
            
            # Verify mask is gone by checking if it's still visible
            for selector in mask_selectors:
                try:
                    mask = await page.query_selector(selector)
                    if mask:
                        is_visible = await mask.is_visible()
                        if is_visible:
                            # Mask still visible, try Escape again
                            await page.keyboard.press('Escape')
                            await asyncio.sleep(1)
                            self.logger.info(f"Mask still visible, pressed Escape again: {selector}")
                except Exception:
                    continue
            
            # If no overlay found, click on a safe area (top-left corner of page)
            try:
                await page.click('body', position={'x': 10, 'y': 10}, timeout=2000)
                await asyncio.sleep(0.5)
                self.logger.info("Closed popup by clicking page background")
            except Exception:
                pass
            
            return True
        except Exception as e:
            self.logger.warning(f"Error closing popup: {str(e)}")
            return False
    
    async def _wait_for_popup_to_close(self, page: Page, timeout: int = 5):
        """Wait for popup/mask to completely disappear"""
        try:
            mask_selectors = [
                '[class*="note-detail-mask"]',
                '[class*="mask"]',
                '.modal-backdrop',
                '[class*="backdrop"]'
            ]
            
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                all_closed = True
                for selector in mask_selectors:
                    try:
                        mask = await page.query_selector(selector)
                        if mask:
                            is_visible = await mask.is_visible()
                            if is_visible:
                                all_closed = False
                                break
                    except Exception:
                        pass
                
                if all_closed:
                    return True
                
                await asyncio.sleep(0.2)
            
            return False
        except Exception:
            return False
    
    async def _extract_note_data(self, page: Page) -> Dict[str, Any]:
        """Extract all data from current note page"""
        note_data = {
            "url": page.url,
            "images": [],
            "text": "",
            "comments": []
        }
        
        try:
            # Extract images
            note_data["images"] = await self._extract_note_images(page)
            
            # Extract text
            note_data["text"] = await self._extract_note_text(page)
            
            # Extract comments
            note_data["comments"] = await self._extract_comments(page)
            
        except Exception as e:
            self.logger.error(f"Error extracting note data: {str(e)}")
        
        return note_data
    
    async def run(
        self, 
        url: str = "", 
        search_keyword: str = "牛奶",
        max_notes: int = 10,
        feishu_webhook_url: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Run the RedNote crawler
        
        Args:
            url: Optional starting URL (defaults to RedNote homepage)
            search_keyword: Keyword to search for (default: "牛奶")
            max_notes: Maximum number of notes to crawl (default: 10)
            feishu_webhook_url: Feishu WebHook URL for notifications
            **kwargs: Additional arguments
            
        Returns:
            JSON string with crawled data
        """
        if feishu_webhook_url:
            self.feishu_webhook_url = feishu_webhook_url
        
        results = {
            "success": False,
            "notes": [],
            "error": None
        }
        
        try:
            # Try to load browser state from Minio before initializing browser
            if self.minio_storage:
                self.logger.info("Attempting to load browser state from Minio...")
                await self._load_browser_state_from_minio()
            
            # Configure browser (non-headless for manual interactions)
            # Use persistent context to save browser state (cookies, localStorage, login session)
            browser_config = BrowserConfig(
                headless=kwargs.get("headless", False),  # Non-headless for login/verification
                verbose=kwargs.get("verbose", True),
                browser_type=kwargs.get("browser_type", "chromium"),
                use_persistent_context=True,  # Enable persistent browser context
                user_data_dir=str(self.browser_data_dir),  # Save browser state to this directory
                use_managed_browser=True  # Required for persistent context
            )
            
            # Initialize crawler
            self.crawler = AsyncWebCrawler(config=browser_config)
            await self.crawler.start()
            
            # Create a session config for consistent page access
            session_config = CrawlerRunConfig(session_id="rednote_session")
            
            # Get page object (need to use the same config for session consistency)
            self.page = await self._get_page(session_config)
            
            # Navigate to RedNote
            start_url = url or self.base_url
            self.logger.info(f"Navigating to: {start_url}")
            await self.page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for page key elements to appear instead of waiting for network idle
            self.logger.info("Waiting for page to be ready...")
            try:
                # Try to wait for search box or any common page element
                search_selectors = [
                    'input[placeholder*="搜索"]',
                    'input[placeholder*="搜索笔记"]',
                    'input[type="search"]',
                    'body'  # Fallback to body element
                ]
                for selector in search_selectors:
                    try:
                        await self.page.wait_for_selector(selector, state="visible", timeout=30000)
                        self.logger.info(f"Page element appeared: {selector}")
                        break
                    except Exception:
                        continue
            except Exception as e:
                self.logger.warning(f"Timeout waiting for elements, continuing anyway: {e}")
            
            await asyncio.sleep(1)  # Brief pause for page to stabilize
            
            # Check for captcha on initial page
            if await self._detect_captcha(self.page):
                await self._handle_verification(self.page)
                # Save browser state after verification (cookies may have been updated)
                await self._save_browser_state_to_minio()
            
            # Check if login is needed
            await self._login_if_needed(self.page)
            # Save browser state after login (session cookies are set)
            await self._save_browser_state_to_minio()
            
            # Search for content
            if not await self._search_content(self.page, search_keyword):
                results["error"] = "Failed to perform search"
                return json.dumps(results, ensure_ascii=False, indent=2)
            
            # Apply filter: click filter button and select "最多点赞"
            self.logger.info("Applying filter: 最多点赞 (Most Likes)...")
            await self._apply_filter_sort(self.page)
            
            # Wait for filtered results to load
            await asyncio.sleep(2)
            
            # Find note elements in the first row (first 5 notes)
            self.logger.info("Finding note elements in the first row...")
            note_elements = []
            
            # Strategy 1: Try common note card selectors
            note_selectors = [
                '.note-item',
                '.feed-item',
                '[class*="note-item"]',
                '[class*="feed-item"]',
                '[class*="note-card"]',
                '.feeds-page .note-item',
                '.search-result-item',
                '[class*="search-result"] [class*="item"]'
            ]
            
            for selector in note_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        note_elements = elements
                        self.logger.info(f"Found {len(elements)} note elements using selector: {selector}")
                        break
                except Exception:
                    continue
            
            # Strategy 2: If no elements found, try to find all clickable items with images
            if not note_elements:
                self.logger.info("Trying alternative strategy: finding clickable items with images...")
                try:
                    # Find elements that contain images and are likely note cards
                    all_elements = await self.page.query_selector_all('a, div[class*="item"], div[class*="card"]')
                    for elem in all_elements:
                        # Check if element contains an image
                        img = await elem.query_selector('img')
                        if img:
                            note_elements.append(elem)
                            if len(note_elements) >= 10:  # Get enough for first row
                                break
                except Exception:
                    pass
            
            if not note_elements:
                results["error"] = "Could not find any note elements"
                return json.dumps(results, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Found {len(note_elements)} potential note elements")
            
            # Store the selector that worked for re-finding elements
            working_selector = None
            for selector in note_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        working_selector = selector
                        break
                except Exception:
                    continue
            
            # If no selector worked, use fallback strategy
            if not working_selector:
                working_selector = 'a, div[class*="item"], div[class*="card"]'
            
            max_notes_to_process = min(max_notes, len(note_elements))
            self.logger.info(f"Processing first {max_notes_to_process} notes")
            
            # Crawl each note by clicking on it and extracting from popup
            # Re-find elements in each iteration to avoid stale element references
            for i in range(1, max_notes_to_process + 1):
                try:
                    self.logger.info(f"Crawling note {i}/{max_notes_to_process} in first row")
                    
                    # Ensure previous popup is completely closed (important for headless mode)
                    if i > 1:
                        self.logger.info(f"Ensuring previous popup is closed before processing note {i}...")
                        await self._close_popup(self.page)
                        await self._wait_for_popup_to_close(self.page, timeout=5)
                        await asyncio.sleep(1)  # Additional wait for page to stabilize
                    
                    # Re-find note elements to avoid stale references after popup closes
                    note_element = None
                    try:
                        elements = await self.page.query_selector_all(working_selector)
                        if elements and len(elements) >= i:
                            note_element = elements[i - 1]  # 0-indexed
                        else:
                            self.logger.warning(f"Could not find note element {i}, found {len(elements) if elements else 0} elements")
                            continue
                    except Exception as e:
                        self.logger.warning(f"Error re-finding note element {i}: {str(e)}")
                        continue
                    
                    # Check if element is still attached to DOM
                    try:
                        is_attached = await note_element.is_visible()
                        if not is_attached:
                            self.logger.warning(f"Note element {i} is not visible, skipping")
                            continue
                    except Exception:
                        self.logger.warning(f"Note element {i} is not attached to DOM, skipping")
                        continue
                    
                    # Scroll element into view
                    try:
                        await note_element.scroll_into_view_if_needed(timeout=5000)
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        self.logger.warning(f"Could not scroll element {i} into view: {str(e)}, trying to continue...")
                        # Try to continue anyway, element might still be clickable
                    
                    # Click the note element to open popup
                    # Use force=True in headless mode to bypass interception
                    try:
                        await self._random_delay(1, 3)
                        # Try normal click first
                        try:
                            await note_element.click(timeout=5000)
                        except Exception:
                            # If normal click fails, try force click (bypasses interception)
                            self.logger.info(f"Normal click failed for note {i}, trying force click...")
                            await note_element.click(force=True, timeout=5000)
                        
                        await asyncio.sleep(2)  # Wait for popup to appear
                        self.logger.info(f"Clicked note {i}, waiting for popup...")
                    except Exception as e:
                        self.logger.warning(f"Could not click element {i}: {str(e)}")
                        continue
                    
                    # Check for captcha
                    if await self._detect_captcha(self.page):
                        await self._handle_verification(self.page)
                    
                    # Extract note data from popup
                    note_data = await self._extract_note_data_from_popup(self.page)
                    note_data["url"] = self.page.url
                    note_data["note_index"] = i
                    note_data["crawled_at"] = datetime.now().isoformat()
                    
                    # Save note data to local storage
                    saved_path = await self._save_note_data(note_data, i)
                    if saved_path:
                        note_data["saved_path"] = saved_path
                    
                    results["notes"].append(note_data)
                    
                    self.logger.info(f"Extracted note {i}: {len(note_data.get('images', []))} images, "
                                   f"{len(note_data.get('text', ''))} chars, {len(note_data.get('comments', []))} comments")
                    
                    # Close popup by clicking outside
                    await self._close_popup(self.page)
                    # Wait for popup to completely close (important for headless mode)
                    await self._wait_for_popup_to_close(self.page, timeout=5)
                    await asyncio.sleep(1)  # Additional wait for page to stabilize
                    
                    self.logger.info(f"Note {i} completed, popup closed")
                        
                except Exception as e:
                    self.logger.error(f"Error crawling note {i}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    # Try to close popup if it's still open
                    try:
                        await self._close_popup(self.page)
                        await self._wait_for_popup_to_close(self.page, timeout=5)
                        await asyncio.sleep(1)
                    except Exception:
                        pass
                    continue
            
            results["success"] = True
            results["total_notes"] = len(results["notes"])
            results["storage_dir"] = str(self.storage_dir)
            
            # Save summary file
            summary_file = self.storage_dir / "summary.json"
            summary = {
                "search_keyword": search_keyword,
                "total_notes": len(results["notes"]),
                "crawled_at": datetime.now().isoformat(),
                "storage_dir": str(self.storage_dir),
                "notes": [
                    {
                        "index": note.get("note_index"),
                        "url": note.get("url"),
                        "images_count": len(note.get("images", [])),
                        "text_length": len(note.get("text", "")),
                        "comments_count": len(note.get("comments", [])),
                        "saved_path": note.get("saved_path")
                    }
                    for note in results["notes"]
                ]
            }
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"\n=== Crawling Complete ===")
            self.logger.info(f"Total notes crawled: {len(results['notes'])}")
            self.logger.info(f"Data saved to: {self.storage_dir}")
            self.logger.info(f"Summary file: {summary_file}")
            
        except Exception as e:
            self.logger.error(f"Crawler error: {str(e)}")
            results["error"] = str(e)
        finally:
            # Save browser state to Minio before closing
            if self.minio_storage:
                self.logger.info("Saving browser state to Minio before closing...")
                await self._save_browser_state_to_minio()
            
            if self.crawler:
                await self.crawler.close()
        
        return json.dumps(results, ensure_ascii=False, indent=2)

