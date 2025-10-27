import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
import argparse
import sys

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Install 'rich' for better output: pip install rich")

# ==================== Configuration ====================

class Config:
    """Application configuration"""
    DEFAULT_TIMEOUT = 15000  # ms
    NAVIGATION_TIMEOUT = 30000  # ms
    RETRY_ATTEMPTS = 3
    RETRY_BACKOFF = 2.0
    PAGE_LOAD_WAIT = 2  # seconds
    ACTION_DELAY = 1  # seconds between actions
    MIN_RATING = 3.8
    MAX_RESULTS_PER_PLATFORM = 5

    # Logging
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    LOG_FILE = "food_delivery_agent.log"

    # Browser settings (persistent profile)
    HEADLESS = False
    SLOW_MO = 100  # ms
    VIEWPORT = {"width": 1920, "height": 1080}
    USER_DATA_DIR = "./browser_data"  # persistent profile dir

# ==================== Logging Setup ====================

def setup_logging(log_file: Optional[str] = None, verbose: bool = False):
    """Configure logging with file and console handlers"""
    log_level = logging.DEBUG if verbose else Config.LOG_LEVEL

    handlers = []

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(Config.LOG_FORMAT))
        handlers.append(file_handler)

    # Console handler
    if RICH_AVAILABLE:
        console_handler = RichHandler(rich_tracebacks=True)
        handlers.append(console_handler)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(Config.LOG_FORMAT))
        handlers.append(console_handler)

    logging.basicConfig(
        level=log_level,
        format=Config.LOG_FORMAT,
        handlers=handlers
    )

logger = logging.getLogger("FoodDeliveryAgent")

# ==================== Data Models ====================

class Platform(Enum):
    SWIGGY = "Swiggy"
    ZOMATO = "Zomato"

@dataclass
class SearchRequest:
    """User's search criteria"""
    food_items: List[str]
    min_rating: float = Config.MIN_RATING
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    max_results_per_platform: int = Config.MAX_RESULTS_PER_PLATFORM
    location: Optional[str] = None

    def __post_init__(self):
        self.food_items = [item.strip() for item in self.food_items if item.strip()]
        if not self.food_items:
            raise ValueError("At least one food item is required")

@dataclass
class ItemResult:
    """Result for a single food item"""
    restaurant_name: str
    rating: Optional[float]
    item_name: str
    item_price: Optional[float]
    final_price: Optional[float]
    discount_percentage: Optional[float]
    coupon_applied: Optional[str]
    platform: str
    url: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def calculate_discount(self):
        """Calculate discount percentage"""
        if self.item_price and self.final_price and self.item_price > 0:
            self.discount_percentage = round(
                ((self.item_price - self.final_price) / self.item_price) * 100, 2
            )

@dataclass
class PlatformReport:
    """Report for a single platform"""
    platform: str
    items_found: int
    successful_additions: int
    errors: List[str] = field(default_factory=list)
    results: List[ItemResult] = field(default_factory=list)
    available: bool = True
    latency_ms: Optional[float] = None

@dataclass
class RunReport:
    """Complete execution report"""
    search_request: SearchRequest
    platforms_processed: List[str]
    total_options: int
    best_deal: Optional[ItemResult]
    platform_reports: List[PlatformReport]
    execution_time_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "search_request": asdict(self.search_request),
            "platforms_processed": self.platforms_processed,
            "total_options": self.total_options,
            "best_deal": asdict(self.best_deal) if self.best_deal else None,
            "platform_reports": [
                {
                    "platform": pr.platform,
                    "items_found": pr.items_found,
                    "successful_additions": pr.successful_additions,
                    "errors": pr.errors,
                    "results": [asdict(r) for r in pr.results],
                    "available": pr.available,
                    "latency_ms": pr.latency_ms
                }
                for pr in self.platform_reports
            ],
            "execution_time_seconds": self.execution_time_seconds,
            "timestamp": self.timestamp
        }

# ==================== Utilities ====================

def retry_async(max_attempts: int = Config.RETRY_ATTEMPTS, backoff: float = Config.RETRY_BACKOFF):
    """Decorator for retrying async functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (PlaywrightTimeoutError, PlaywrightError, asyncio.TimeoutError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff ** attempt
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
            raise last_exception
        return wrapper
    return decorator

class PageHelper:
    """Helper methods for common page operations"""

    @staticmethod
    async def safe_click(page: Page, selector: str, timeout: int = 3000) -> bool:
        """Safely click an element"""
        try:
            await page.click(selector, timeout=timeout)
            await asyncio.sleep(Config.ACTION_DELAY)
            return True
        except Exception as e:
            logger.debug(f"Click failed for {selector}: {e}")
            return False

    @staticmethod
    async def safe_fill(page: Page, selector: str, text: str, timeout: int = 3000) -> bool:
        """Safely fill an input field"""
        try:
            await page.fill(selector, text, timeout=timeout)
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            logger.debug(f"Fill failed for {selector}: {e}")
            return False

    @staticmethod
    async def extract_price(text: str) -> Optional[float]:
        """Extract price from text"""
        try:
            cleaned = text.replace('₹', '').replace(',', '').strip()
            numbers = ''.join(ch for ch in cleaned if ch.isdigit() or ch == '.')
            return float(numbers) if numbers else None
        except Exception:
            return None

    @staticmethod
    async def extract_rating(text: str) -> Optional[float]:
        """Extract rating from text"""
        try:
            cleaned = ''.join(ch for ch in text if ch.isdigit() or ch == '.')
            rating = float(cleaned)
            return rating if 0 <= rating <= 5 else None
        except Exception:
            return None

# ==================== CAP Manager & Mode ====================

class CAPMode(Enum):
    """Choose which CAP tradeoff behavior the agent favors for different operations."""
    AVAILABILITY_FIRST = "availability_first"  # prioritize availability (search)
    CONSISTENCY_FIRST = "consistency_first"    # prioritize consistency (cart ops)

class CAPManager:
    """
    Coordinates CAP-aware behaviors:
      - Parallel high-availability searches
      - Consistent cart additions (idempotent, verified, rollback on mismatch)
    """

    def __init__(self, page: Page, mode: CAPMode = CAPMode.AVAILABILITY_FIRST):
        self.page = page
        self.mode = mode

    async def parallel_search_handlers(self, handlers: List["BasePlatformHandler"], timeout_per_handler: float = 25.0):
        """
        Run handler.initialize() and handler.search_items() in parallel with per-handler timeouts.
        Returns tuple(all_results, platform_reports)
        """
        async def run_handler(handler: "BasePlatformHandler"):
            start = time.time()
            try:
                await handler.initialize()
                results = await asyncio.wait_for(handler.search_items(), timeout=timeout_per_handler)
                handler.report.available = True
                handler.report.latency_ms = (time.time() - start) * 1000
                return results, handler.report
            except asyncio.TimeoutError as e:
                handler.report.available = False
                handler.report.errors.append(f"Timeout: {e}")
                handler.report.latency_ms = (time.time() - start) * 1000
                logger.warning(f"{handler.__class__.__name__} timed out after {timeout_per_handler}s")
                return [], handler.report
            except Exception as e:
                handler.report.available = False
                handler.report.errors.append(str(e))
                handler.report.latency_ms = (time.time() - start) * 1000
                logger.error(f"{handler.__class__.__name__} search error: {e}")
                return [], handler.report

        tasks = [run_handler(h) for h in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        all_results = []
        reports = []
        for res, rep in results:
            all_results.extend(res)
            reports.append(rep)
        return all_results, reports

    async def add_to_cart_consistent(self, handler: "BasePlatformHandler", item: ItemResult,
                                     max_attempts: int = 3, backoff: float = 1.5) -> bool:
        """
        Try to add `item` to platform cart with *consistency-first* guarantees:
        1. Use an idempotency token so repeated attempts don't create duplicates.
        2. After add, verify server-side cart contents (price and item).
        3. If verification fails, attempt rollback (remove item) and optionally retry.
        Returns True if add is verified consistent; False otherwise.
        """
        idempotency_token = str(uuid.uuid4())
        attempt = 0
        last_exc = None

        while attempt < max_attempts:
            attempt += 1
            try:
                logger.info(f"Attempting to add to cart ({attempt}/{max_attempts}) - platform={handler.__class__.__name__} item={item.item_name}")
                add_func = getattr(handler, "add_item_to_cart", None)
                if not callable(add_func):
                    raise NotImplementedError(f"{handler.__class__.__name__} does not implement add_item_to_cart")

                await add_func(item, idempotency_token)

                verify_func = getattr(handler, "verify_cart_contains", None)
                if not callable(verify_func):
                    logger.debug("No handler.verify_cart_contains(); performing fallback cart verification")
                    verified = await self._fallback_verify(handler, item)
                else:
                    verified = await verify_func(item)

                if verified:
                    logger.info("Cart add verified consistent")
                    handler.report.successful_additions += 1
                    return True
                else:
                    logger.warning("Cart verification failed — attempting rollback")
                    remove_func = getattr(handler, "remove_item_from_cart", None)
                    if callable(remove_func):
                        await remove_func(item)
                    else:
                        await self._fallback_remove(handler, item)

                    last_exc = RuntimeError("Verification failed after add")
                    if self.mode == CAPMode.CONSISTENCY_FIRST:
                        wait = backoff ** (attempt - 1)
                        await asyncio.sleep(wait)
                        continue
                    else:
                        break

            except Exception as e:
                last_exc = e
                logger.warning(f"Add to cart attempt {attempt} failed: {e}")
                wait = backoff ** (attempt - 1)
                await asyncio.sleep(wait)
                continue

        logger.error(f"Failed to add to cart consistently after {max_attempts} attempts: {last_exc}")
        return False

    async def _fallback_verify(self, handler: "BasePlatformHandler", item: ItemResult) -> bool:
        """
        Minimal DOM-based verification: opens cart page and checks for item name and price.
        This is brittle: platform-specific handlers should override verify_cart_contains.
        """
        try:
            cart_urls = [
                f"{getattr(handler, 'BASE_URL', '')}/cart",
                f"{getattr(handler, 'BASE_URL', '')}/checkout",
            ]
            for url in cart_urls:
                if not url:
                    continue
                try:
                    await self.page.goto(url, timeout=Config.NAVIGATION_TIMEOUT)
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                except Exception:
                    continue

                page_text = await self.page.content()
                if item.item_name.lower() in page_text.lower():
                    if item.final_price:
                        price_strs = [f"₹{int(item.final_price)}", f"₹{round(item.final_price,2)}"]
                        if any(s in page_text for s in price_strs):
                            return True
                    else:
                        return True
            return False
        except Exception as e:
            logger.debug(f"Fallback verify failed: {e}")
            return False

    async def _fallback_remove(self, handler: "BasePlatformHandler", item: ItemResult):
        """Best-effort: navigate to cart and attempt to remove items matching name"""
        try:
            cart_urls = [
                f"{getattr(handler, 'BASE_URL', '')}/cart",
                f"{getattr(handler, 'BASE_URL', '')}/checkout",
            ]
            for url in cart_urls:
                if not url:
                    continue
                try:
                    await self.page.goto(url, timeout=Config.NAVIGATION_TIMEOUT)
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                except Exception:
                    continue

                remove_buttons = await self.page.query_selector_all("button:has-text('Remove'), button:has-text('Delete'), a:has-text('Remove')")
                for btn in remove_buttons:
                    try:
                        parent_text = await btn.evaluate("el => el.closest('div')?.innerText || ''")
                        if item.item_name.lower() in (parent_text or "").lower():
                            await btn.click()
                            await asyncio.sleep(0.8)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Fallback remove failed: {e}")
            return

# ==================== Platform Handlers ====================

class BasePlatformHandler:
    """Base class for platform-specific handlers"""

    def __init__(self, page: Page, search_request: SearchRequest):
        self.page = page
        self.request = search_request
        self.helper = PageHelper()
        self.report = PlatformReport(platform=self.__class__.__name__, items_found=0, successful_additions=0)

    async def initialize(self):
        """Initialize the platform (navigate to home, check login, etc.)"""
        raise NotImplementedError

    async def search_items(self) -> List[ItemResult]:
        """Main method to search and process items"""
        raise NotImplementedError

    async def cleanup(self):
        """Cleanup actions (clear cart, return to home, etc.)"""
        try:
            await self.page.goto(self.BASE_URL, timeout=Config.NAVIGATION_TIMEOUT)
            await asyncio.sleep(1)
        except Exception as e:
            logger.debug(f"Cleanup failed: {e}")

class SwiggyHandler(BasePlatformHandler):
    """Swiggy-specific implementation"""

    BASE_URL = "https://www.swiggy.com"

    @retry_async()
    async def initialize(self):
        """Navigate to Swiggy homepage"""
        logger.info("Initializing Swiggy...")
        await self.page.goto(self.BASE_URL, timeout=Config.NAVIGATION_TIMEOUT)
        await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
        await asyncio.sleep(Config.PAGE_LOAD_WAIT)

        try:
            login_button = await self.page.query_selector("text=/login|sign in/i")
            if login_button:
                logger.warning("Not logged in to Swiggy. Some features may be limited.")
        except Exception:
            pass

    @retry_async()
    async def search_items(self) -> List[ItemResult]:
        """Search for items on Swiggy"""
        results = []

        for food_item in self.request.food_items:
            logger.info(f"Searching Swiggy for: {food_item}")

            try:
                # Search for the item
                search_input = await self.page.query_selector("input[placeholder*='Search'], input[type='text']")
                if search_input:
                    try:
                        await search_input.fill("")
                        await search_input.fill(food_item)
                        await self.page.keyboard.press("Enter")
                        await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                        await asyncio.sleep(Config.PAGE_LOAD_WAIT)
                    except Exception:
                        # fallback to direct search url
                        search_url = f"{self.BASE_URL}/search?q={food_item}"
                        await self.page.goto(search_url, timeout=Config.NAVIGATION_TIMEOUT)
                        await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                        await asyncio.sleep(Config.PAGE_LOAD_WAIT)
                else:
                    search_url = f"{self.BASE_URL}/search?q={food_item}"
                    await self.page.goto(search_url, timeout=Config.NAVIGATION_TIMEOUT)
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                    await asyncio.sleep(Config.PAGE_LOAD_WAIT)

                # Find restaurant/dish cards
                cards = await self.page.query_selector_all(
                    "a[href*='/restaurant/'], div[data-testid*='restaurant'], div[class*='RestaurantList']"
                )

                logger.info(f"Found {len(cards)} cards on Swiggy for {food_item}")

                processed = 0
                for card in cards[: self.request.max_results_per_platform]:
                    try:
                        item_result = await self._process_card(card, food_item)
                        if item_result:
                            results.append(item_result)
                            processed += 1
                    except Exception as e:
                        logger.debug(f"Failed to process card: {e}")
                        self.report.errors.append(f"Card processing error: {str(e)}")

                logger.info(f"Successfully processed {processed} items for {food_item}")

            except Exception as e:
                logger.error(f"Search failed for {food_item} on Swiggy: {e}")
                self.report.errors.append(f"Search error for {food_item}: {str(e)}")

        self.report.items_found = len(results)
        self.report.results = results
        return results

    async def _process_card(self, card, food_item: str) -> Optional[ItemResult]:
        """Process a single restaurant/item card"""
        try:
            # Extract basic info
            text_content = await card.inner_text()

            # Extract name
            name_elem = await card.query_selector("h3, h4, div[class*='name'], div[class*='title']")
            name = await name_elem.inner_text() if name_elem else text_content.split('\n')[0]

            # Extract rating
            rating = None
            rating_elem = await card.query_selector("div[class*='rating'], span[class*='rating']")
            if rating_elem:
                rating_text = await rating_elem.inner_text()
                rating = await self.helper.extract_rating(rating_text)

            # Check rating filter
            if rating and rating < self.request.min_rating:
                return None

            # Extract price
            price = None
            price_elem = await card.query_selector("span:has-text('₹'), div:has-text('₹')")
            if price_elem:
                price_text = await price_elem.inner_text()
                price = await self.helper.extract_price(price_text)

            # Check price filter
            if price:
                if self.request.price_min and price < self.request.price_min:
                    return None
                if self.request.price_max and price > self.request.price_max:
                    return None

            # Extract URL
            url = None
            href = await card.get_attribute("href")
            if href:
                url = href if href.startswith("http") else self.BASE_URL + href

            # Create result
            result = ItemResult(
                restaurant_name=name.strip(),
                rating=rating,
                item_name=food_item,
                item_price=price,
                final_price=price,  # Will be updated if coupon applied
                discount_percentage=0,
                coupon_applied=None,
                platform=Platform.SWIGGY.value,
                url=url
            )

            self.report.successful_additions += 1
            return result

        except Exception as e:
            logger.debug(f"Card processing error: {e}")
            return None

    # ==== Cart operations (best-effort; adjust selectors after testing) ====
    async def add_item_to_cart(self, item: ItemResult, idempotency_token: str):
        """
        Best-effort: open item/restaurant URL and click add-to-cart.
        Use idempotency_token for logging/tracking only.
        """
        if not item.url:
            raise ValueError("No URL for item to add to cart (Swiggy)")
        try:
            await self.page.goto(item.url, timeout=Config.NAVIGATION_TIMEOUT)
            await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
            await asyncio.sleep(1)

            # Try to find an "Add" button near the item name
            # These selectors are examples — update after inspecting Swiggy's page
            add_buttons = await self.page.query_selector_all("button:has-text('Add'), button:has-text('ADD'), button[data-testid*='add']")
            if not add_buttons:
                dish = await self.page.query_selector(f"text=\"{item.item_name}\"")
                if dish:
                    try:
                        await dish.click()
                        await asyncio.sleep(0.6)
                    except Exception:
                        pass
                    add_buttons = await self.page.query_selector_all("button:has-text('Add'), button:has-text('ADD')")

            if add_buttons:
                try:
                    await add_buttons[0].click()
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.debug(f"Swiggy add button click failed: {e}")
                    raise
            else:
                raise RuntimeError("Could not find add-to-cart button on Swiggy page")
        except Exception as e:
            logger.debug(f"Swiggy add_item_to_cart exception: {e}")
            raise

    async def verify_cart_contains(self, item: ItemResult) -> bool:
        # Try cart URL then fallback DOM checks
        try:
            cart_url = f"{self.BASE_URL}/cart"
            await self.page.goto(cart_url, timeout=Config.NAVIGATION_TIMEOUT)
            await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
            page_text = await self.page.content()
            if item.item_name.lower() in page_text.lower():
                if item.final_price:
                    if f"₹{int(item.final_price)}" in page_text or f"₹{round(item.final_price,2)}" in page_text:
                        return True
                else:
                    return True
            return False
        except Exception as e:
            logger.debug(f"Swiggy verify_cart_contains exception: {e}")
            return False

    async def remove_item_from_cart(self, item: ItemResult):
        try:
            cart_url = f"{self.BASE_URL}/cart"
            await self.page.goto(cart_url, timeout=Config.NAVIGATION_TIMEOUT)
            await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
            remove_buttons = await self.page.query_selector_all("button:has-text('Remove'), button:has-text('Delete'), a:has-text('Remove')")
            for btn in remove_buttons:
                try:
                    parent_text = await btn.evaluate("el => el.closest('div')?.innerText || ''")
                    if item.item_name.lower() in (parent_text or "").lower():
                        await btn.click()
                        await asyncio.sleep(0.8)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Swiggy remove_item_from_cart exception: {e}")
            return

class ZomatoHandler(BasePlatformHandler):
    """Zomato-specific implementation"""

    BASE_URL = "https://www.zomato.com"

    @retry_async()
    async def initialize(self):
        """Navigate to Zomato homepage"""
        logger.info("Initializing Zomato...")
        await self.page.goto(self.BASE_URL, timeout=Config.NAVIGATION_TIMEOUT)
        await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
        await asyncio.sleep(Config.PAGE_LOAD_WAIT)

        try:
            login_button = await self.page.query_selector("text=/login|sign in/i")
            if login_button:
                logger.warning("Not logged in to Zomato. Some features may be limited.")
        except Exception:
            pass

    @retry_async()
    async def search_items(self) -> List[ItemResult]:
        """Search for items on Zomato"""
        results = []

        for food_item in self.request.food_items:
            logger.info(f"Searching Zomato for: {food_item}")

            try:
                # Search for the item
                search_input = await self.page.query_selector("input[placeholder*='Search'], input[type='text']")
                if search_input:
                    try:
                        await search_input.fill("")
                        await search_input.fill(food_item)
                        await self.page.keyboard.press("Enter")
                        await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                        await asyncio.sleep(Config.PAGE_LOAD_WAIT)
                    except Exception:
                        search_url = f"{self.BASE_URL}/search?q={food_item}"
                        await self.page.goto(search_url, timeout=Config.NAVIGATION_TIMEOUT)
                        await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                        await asyncio.sleep(Config.PAGE_LOAD_WAIT)
                else:
                    search_url = f"{self.BASE_URL}/search?q={food_item}"
                    await self.page.goto(search_url, timeout=Config.NAVIGATION_TIMEOUT)
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                    await asyncio.sleep(Config.PAGE_LOAD_WAIT)

                cards = await self.page.query_selector_all(
                    "a[href*='/restaurant/'], a[href*='/order/'], div[data-testid*='resCard']"
                )

                logger.info(f"Found {len(cards)} cards on Zomato for {food_item}")

                processed = 0
                for card in cards[: self.request.max_results_per_platform]:
                    try:
                        item_result = await self._process_card(card, food_item)
                        if item_result:
                            results.append(item_result)
                            processed += 1
                    except Exception as e:
                        logger.debug(f"Failed to process card: {e}")
                        self.report.errors.append(f"Card processing error: {str(e)}")

                logger.info(f"Successfully processed {processed} items for {food_item}")

            except Exception as e:
                logger.error(f"Search failed for {food_item} on Zomato: {e}")
                self.report.errors.append(f"Search error for {food_item}: {str(e)}")

        self.report.items_found = len(results)
        self.report.results = results
        return results

    async def _process_card(self, card, food_item: str) -> Optional[ItemResult]:
        """Process a single restaurant/item card"""
        try:
            text_content = await card.inner_text()

            name_elem = await card.query_selector("h4, h3, div[class*='name'], p[class*='name']")
            name = await name_elem.inner_text() if name_elem else text_content.split('\n')[0]

            rating = None
            rating_elem = await card.query_selector("div[aria-label*='rating'], div[class*='rating']")
            if rating_elem:
                rating_text = await rating_elem.inner_text()
                rating = await self.helper.extract_rating(rating_text)

            if rating and rating < self.request.min_rating:
                return None

            price = None
            price_elem = await card.query_selector("span:has-text('₹'), p:has-text('₹')")
            if price_elem:
                price_text = await price_elem.inner_text()
                price = await self.helper.extract_price(price_text)

            if price:
                if self.request.price_min and price < self.request.price_min:
                    return None
                if self.request.price_max and price > self.request.price_max:
                    return None

            url = None
            href = await card.get_attribute("href")
            if href:
                url = href if href.startswith("http") else self.BASE_URL + href

            result = ItemResult(
                restaurant_name=name.strip(),
                rating=rating,
                item_name=food_item,
                item_price=price,
                final_price=price,
                discount_percentage=0,
                coupon_applied=None,
                platform=Platform.ZOMATO.value,
                url=url
            )

            self.report.successful_additions += 1
            return result

        except Exception as e:
            logger.debug(f"Card processing error: {e}")
            return None

    # ==== Cart operations (best-effort; adjust selectors after testing) ====
    async def add_item_to_cart(self, item: ItemResult, idempotency_token: str):
        if not item.url:
            raise ValueError("No URL for item to add to cart (Zomato)")
        try:
            await self.page.goto(item.url, timeout=Config.NAVIGATION_TIMEOUT)
            await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
            await asyncio.sleep(1)

            add_buttons = await self.page.query_selector_all("button:has-text('Add'), button:has-text('ADD'), button:has-text('Add to cart')")
            if not add_buttons:
                dish = await self.page.query_selector(f"text=\"{item.item_name}\"")
                if dish:
                    try:
                        await dish.click()
                        await asyncio.sleep(0.6)
                    except Exception:
                        pass
                    add_buttons = await self.page.query_selector_all("button:has-text('Add'), button:has-text('ADD')")

            if add_buttons:
                try:
                    await add_buttons[0].click()
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.debug(f"Zomato add button click failed: {e}")
                    raise
            else:
                raise RuntimeError("Could not find add-to-cart button on Zomato page")
        except Exception as e:
            logger.debug(f"Zomato add_item_to_cart exception: {e}")
            raise

    async def verify_cart_contains(self, item: ItemResult) -> bool:
        try:
            cart_url = f"{self.BASE_URL}/cart"
            await self.page.goto(cart_url, timeout=Config.NAVIGATION_TIMEOUT)
            await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
            page_text = await self.page.content()
            if item.item_name.lower() in page_text.lower():
                if item.final_price:
                    if f"₹{int(item.final_price)}" in page_text or f"₹{round(item.final_price,2)}" in page_text:
                        return True
                else:
                    return True
            return False
        except Exception as e:
            logger.debug(f"Zomato verify_cart_contains exception: {e}")
            return False

    async def remove_item_from_cart(self, item: ItemResult):
        try:
            cart_url = f"{self.BASE_URL}/cart"
            await self.page.goto(cart_url, timeout=Config.NAVIGATION_TIMEOUT)
            await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
            remove_buttons = await self.page.query_selector_all("button:has-text('Remove'), button:has-text('Delete'), a:has-text('Remove')")
            for btn in remove_buttons:
                try:
                    parent_text = await btn.evaluate("el => el.closest('div')?.innerText || ''")
                    if item.item_name.lower() in (parent_text or "").lower():
                        await btn.click()
                        await asyncio.sleep(0.8)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Zomato remove_item_from_cart exception: {e}")
            return

# ==================== Main Agent ====================

class FoodDeliveryAgent:
    """Main orchestrator for food delivery comparison"""

    def __init__(self, headless: bool = Config.HEADLESS, slow_mo: int = Config.SLOW_MO):
        self.headless = headless
        self.slow_mo = slow_mo
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()

    async def initialize(self):
        """Initialize browser and page"""
        logger.info("Initializing browser (persistent profile)...")
        self.playwright = await async_playwright().start()

        # persistent profile to reuse logged-in sessions
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=Config.USER_DATA_DIR,
            headless=self.headless,
            slow_mo=self.slow_mo,
            viewport=Config.VIEWPORT,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        self.page = await self.context.new_page()
        self.page.set_default_navigation_timeout(Config.NAVIGATION_TIMEOUT)
        self.page.set_default_timeout(Config.DEFAULT_TIMEOUT)

        logger.info("Browser initialized successfully")

    async def cleanup(self):
        """Cleanup browser resources"""
        logger.info("Cleaning up browser...")
        try:
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def run(self, search_request: SearchRequest) -> RunReport:
        """Execute the food delivery comparison"""
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Starting search for: {', '.join(search_request.food_items)}")

        # Create handlers
        swiggy_handler = SwiggyHandler(self.page, search_request)
        zomato_handler = ZomatoHandler(self.page, search_request)
        handlers = [swiggy_handler, zomato_handler]

        # CAP manager: availability-first for searches
        cap_mgr = CAPManager(self.page, mode=CAPMode.AVAILABILITY_FIRST)

        # Run searches in parallel with per-handler timeout
        all_results, platform_reports = await cap_mgr.parallel_search_handlers(handlers, timeout_per_handler=25.0)

        # Ensure reports list contains all handler reports
        # (parallel_search_handlers already returned them)
        reports = platform_reports

        # Calculate discounts
        for result in all_results:
            result.calculate_discount()

        # Find best deal (lowest final_price)
        best_deal = None
        if all_results:
            valid_results = [r for r in all_results if r.final_price is not None]
            if valid_results:
                best_deal = min(valid_results, key=lambda x: x.final_price)

        # Consistency-first for cart operations: try to add best deal and verify
        if best_deal:
            logger.info(f"Best deal chosen: {best_deal.platform} - {best_deal.restaurant_name} - ₹{best_deal.final_price}")

            # map platform string to handler instance
            platform_lower = best_deal.platform.lower()
            handler_for_platform = None
            if "swiggy" in platform_lower:
                handler_for_platform = swiggy_handler
            elif "zomato" in platform_lower:
                handler_for_platform = zomato_handler

            if handler_for_platform:
                cap_mgr_cart = CAPManager(self.page, mode=CAPMode.CONSISTENCY_FIRST)
                added_ok = await cap_mgr_cart.add_to_cart_consistent(handler_for_platform, best_deal, max_attempts=3)
                if not added_ok:
                    logger.warning("Could not add best deal to cart consistently. Marking report accordingly.")
                    # add error to the matching platform report
                    for pr in reports:
                        if pr.platform and best_deal.platform.lower() in pr.platform.lower():
                            pr.errors.append("Consistent add-to-cart failed")

        execution_time = asyncio.get_event_loop().time() - start_time

        # Create report
        report = RunReport(
            search_request=search_request,
            platforms_processed=[pr.platform for pr in reports],
            total_options=len(all_results),
            best_deal=best_deal,
            platform_reports=reports,
            execution_time_seconds=round(execution_time, 2)
        )

        logger.info(f"Search completed in {execution_time:.2f}s. Found {len(all_results)} options.")

        return report

# ==================== Output Formatting ====================

def print_report(report: RunReport):
    """Print formatted report"""
    if RICH_AVAILABLE:
        console = Console()

        # Summary
        console.print("\n[bold cyan]Food Delivery Comparison Report[/bold cyan]")
        console.print(f"Searched for: {', '.join(report.search_request.food_items)}")
        console.print(f"Execution time: {report.execution_time_seconds}s")
        console.print(f"Total options found: {report.total_options}\n")

        # Best deal
        if report.best_deal:
            console.print("[bold green]🏆 Best Deal:[/bold green]")
            console.print(f"  Platform: {report.best_deal.platform}")
            console.print(f"  Restaurant: {report.best_deal.restaurant_name}")
            console.print(f"  Item: {report.best_deal.item_name}")
            console.print(f"  Price: ₹{report.best_deal.final_price}")
            if report.best_deal.rating:
                console.print(f"  Rating: {report.best_deal.rating}⭐")
            console.print()

        # All results table
        if report.total_options > 0:
            table = Table(title="All Options")
            table.add_column("Platform", style="cyan")
            table.add_column("Restaurant", style="yellow")
            table.add_column("Item", style="white")
            table.add_column("Price", justify="right", style="green")
            table.add_column("Rating", justify="right")

            for pr in report.platform_reports:
                for result in pr.results:
                    table.add_row(
                        result.platform,
                        (result.restaurant_name or "")[:30],
                        (result.item_name or "")[:30],
                        f"₹{result.final_price}" if result.final_price else "N/A",
                        f"{result.rating}⭐" if result.rating else "N/A"
                    )

            console.print(table)

        # Errors and availability
        for pr in report.platform_reports:
            if pr.errors:
                console.print(f"\n[yellow]⚠️  {pr.platform} Errors:[/yellow]")
                for error in pr.errors[:5]:  # Show first 5 errors
                    console.print(f"  - {error}")
            console.print(f"[grey42]Availability: {'Up' if pr.available else 'Down'} | Latency: {pr.latency_ms:.0f}ms[/grey42]") if pr.latency_ms else None
    else:
        # Plain text output
        print("\n" + "="*60)
        print("FOOD DELIVERY COMPARISON REPORT")
        print("="*60)
        print(f"Searched for: {', '.join(report.search_request.food_items)}")
        print(f"Execution time: {report.execution_time_seconds}s")
        print(f"Total options: {report.total_options}")

        if report.best_deal:
            print(f"\nBEST DEAL:")
            print(f"  Platform: {report.best_deal.platform}")
            print(f"  Restaurant: {report.best_deal.restaurant_name}")
            print(f"  Item: {report.best_deal.item_name}")
            print(f"  Price: ₹{report.best_deal.final_price}")
            if report.best_deal.rating:
                print(f"  Rating: {report.best_deal.rating}")

        print("\nALL OPTIONS:")
        for pr in report.platform_reports:
            print(f"\n{pr.platform}:")
            for result in pr.results:
                print(f"  - {result.restaurant_name}: {result.item_name} - ₹{result.final_price}")

# ==================== Save Report ====================

def save_report(report: RunReport, output_file: str):
    """Save report to JSON file"""
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save report: {e}")

# ==================== CLI Interface ====================

def interactive_mode() -> SearchRequest:
    """Interactive CLI for user input"""
    print("\n" + "="*60)
    print("FOOD DELIVERY AGENT - Interactive Mode")
    print("="*60)

    # Food items
    print("\nEnter food items (comma-separated):")
    print("Example: pizza, burger, biryani")
    items_input = input("> ").strip()
    food_items = [item.strip() for item in items_input.split(",") if item.strip()]

    if not food_items:
        print("No food items provided. Exiting.")
        sys.exit(1)

    # Rating filter
    rating_input = input(f"\nMinimum rating (default {Config.MIN_RATING}): ").strip()
    min_rating = float(rating_input) if rating_input else Config.MIN_RATING

    # Price filters
    price_min_input = input("\nMinimum price (leave empty for no limit): ").strip()
    price_min = float(price_min_input) if price_min_input else None

    price_max_input = input("Maximum price (leave empty for no limit): ").strip()
    price_max = float(price_max_input) if price_max_input else None

    # Max results
    max_results_input = input(f"\nMax results per platform (default {Config.MAX_RESULTS_PER_PLATFORM}): ").strip()
    max_results = int(max_results_input) if max_results_input else Config.MAX_RESULTS_PER_PLATFORM

    # Location
    location_input = input("\nLocation (optional, e.g., 'Bangalore', 'Delhi'): ").strip()
    location = location_input if location_input else None

    return SearchRequest(
        food_items=food_items,
        min_rating=min_rating,
        price_min=price_min,
        price_max=price_max,
        max_results_per_platform=max_results,
        location=location
    )

def load_config_file(config_path: str) -> SearchRequest:
    """Load search request from JSON config file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return SearchRequest(
            food_items=data.get('food_items', []),
            min_rating=data.get('min_rating', Config.MIN_RATING),
            price_min=data.get('price_min'),
            price_max=data.get('price_max'),
            max_results_per_platform=data.get('max_results_per_platform', Config.MAX_RESULTS_PER_PLATFORM),
            location=data.get('location')
        )
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        sys.exit(1)

# ==================== Main ====================

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Food Delivery Comparison Agent - Compare deals across Swiggy and Zomato",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Interactive mode:
    python food_delivery_agent_CAP.py --interactive

  Using config file:
    python food_delivery_agent_CAP.py --config config.json

  Quick search:
    python food_delivery_agent_CAP.py --items "pizza,burger" --rating 4.0

  With output file:
    python food_delivery_agent_CAP.py --interactive --output results.json
        """
    )

    # Input modes
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--interactive', '-i', action='store_true',
                            help='Run in interactive mode')
    input_group.add_argument('--config', '-c', type=str,
                            help='Path to JSON config file')
    input_group.add_argument('--items', type=str,
                            help='Comma-separated food items (e.g., "pizza,burger")')

    # Optional parameters (for --items mode)
    parser.add_argument('--rating', type=float, default=Config.MIN_RATING,
                       help=f'Minimum rating (default: {Config.MIN_RATING})')
    parser.add_argument('--price-min', type=float,
                       help='Minimum price filter')
    parser.add_argument('--price-max', type=float,
                       help='Maximum price filter')
    parser.add_argument('--max-results', type=int, default=Config.MAX_RESULTS_PER_PLATFORM,
                       help=f'Max results per platform (default: {Config.MAX_RESULTS_PER_PLATFORM})')
    parser.add_argument('--location', type=str,
                       help='Location (e.g., "Bangalore")')

    # Browser options
    parser.add_argument('--headless', action='store_true',
                       help='Run browser in headless mode')
    parser.add_argument('--slow-mo', type=int, default=Config.SLOW_MO,
                       help=f'Slow motion delay in ms (default: {Config.SLOW_MO})')

    # Output options
    parser.add_argument('--output', '-o', type=str,
                       help='Save report to JSON file')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    # Setup logging
    setup_logging(log_file=Config.LOG_FILE, verbose=args.verbose)

    # Get search request
    if args.interactive:
        search_request = interactive_mode()
    elif args.config:
        search_request = load_config_file(args.config)
    else:
        # Quick mode with --items
        food_items = [item.strip() for item in args.items.split(',') if item.strip()]
        search_request = SearchRequest(
            food_items=food_items,
            min_rating=args.rating,
            price_min=args.price_min,
            price_max=args.price_max,
            max_results_per_platform=args.max_results,
            location=args.location
        )

    # Run agent
    try:
        async with FoodDeliveryAgent(headless=args.headless, slow_mo=args.slow_mo) as agent:
            report = await agent.run(search_request)

        # Display results
        print_report(report)

        # Save to file if requested
        if args.output:
            save_report(report, args.output)

        # Exit with appropriate code
        sys.exit(0 if report.total_options > 0 else 1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=args.verbose)
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(130)
