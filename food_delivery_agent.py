"""
Food Delivery Comparison Agent - Production Version

A robust, production-ready agent for comparing food deals across Swiggy and Zomato.
Uses Playwright with Chromium for consistent, reliable automation.

Installation:
    pip install playwright rich pydantic
    playwright install chromium

Usage:
    python food_delivery_agent.py --config config.json
    python food_delivery_agent.py --interactive
"""

import asyncio
import json
import logging
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

    # Browser settings
    HEADLESS = False
    SLOW_MO = 100  # ms
    VIEWPORT = {"width": 1920, "height": 1080}


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
                    "results": [asdict(r) for r in pr.results]
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
                except (PlaywrightTimeoutError, PlaywrightError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff ** attempt
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts")
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

        # Check if logged in
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
                    await search_input.fill("")
                    await search_input.fill(food_item)
                    await self.page.keyboard.press("Enter")
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                    await asyncio.sleep(Config.PAGE_LOAD_WAIT)
                else:
                    # Fallback: direct URL
                    search_url = f"{self.BASE_URL}/search?q={food_item}"
                    await self.page.goto(search_url, timeout=Config.NAVIGATION_TIMEOUT)
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)

                # Find restaurant/dish cards
                cards = await self.page.query_selector_all(
                    "a[href*='/restaurant/'], div[data-testid*='restaurant'], div[class*='RestaurantList']"
                )

                logger.info(f"Found {len(cards)} cards on Swiggy for {food_item}")

                processed = 0
                for card in cards[:self.request.max_results_per_platform]:
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

        # Check if logged in
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
                    await search_input.fill("")
                    await search_input.fill(food_item)
                    await self.page.keyboard.press("Enter")
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)
                    await asyncio.sleep(Config.PAGE_LOAD_WAIT)
                else:
                    # Fallback: direct URL
                    search_url = f"{self.BASE_URL}/search?q={food_item}"
                    await self.page.goto(search_url, timeout=Config.NAVIGATION_TIMEOUT)
                    await self.page.wait_for_load_state("networkidle", timeout=Config.DEFAULT_TIMEOUT)

                # Find restaurant/dish cards
                cards = await self.page.query_selector_all(
                    "a[href*='/restaurant/'], a[href*='/order/'], div[data-testid*='resCard']"
                )

                logger.info(f"Found {len(cards)} cards on Zomato for {food_item}")

                processed = 0
                for card in cards[:self.request.max_results_per_platform]:
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
            # Extract basic info
            text_content = await card.inner_text()

            # Extract name
            name_elem = await card.query_selector("h4, h3, div[class*='name'], p[class*='name']")
            name = await name_elem.inner_text() if name_elem else text_content.split('\n')[0]

            # Extract rating
            rating = None
            rating_elem = await card.query_selector("div[aria-label*='rating'], div[class*='rating']")
            if rating_elem:
                rating_text = await rating_elem.inner_text()
                rating = await self.helper.extract_rating(rating_text)

            # Check rating filter
            if rating and rating < self.request.min_rating:
                return None

            # Extract price
            price = None
            price_elem = await card.query_selector("span:has-text('₹'), p:has-text('₹')")
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


# ==================== Main Agent ====================

class FoodDeliveryAgent:
    """Main orchestrator for food delivery comparison"""

    def __init__(self, headless: bool = Config.HEADLESS, slow_mo: int = Config.SLOW_MO):
        self.headless = headless
        self.slow_mo = slow_mo
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()

    async def initialize(self):
        """Initialize browser and page"""
        logger.info("Initializing browser...")
        self.playwright = await async_playwright().start()

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
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

        platform_reports = []
        all_results = []

        # Process Swiggy
        try:
            swiggy_handler = SwiggyHandler(self.page, search_request)
            await swiggy_handler.initialize()
            swiggy_results = await swiggy_handler.search_items()
            all_results.extend(swiggy_results)
            platform_reports.append(swiggy_handler.report)
            await swiggy_handler.cleanup()
        except Exception as e:
            logger.error(f"Swiggy processing failed: {e}")
            platform_reports.append(PlatformReport(
                platform="Swiggy",
                items_found=0,
                successful_additions=0,
                errors=[str(e)]
            ))

        # Process Zomato
        try:
            zomato_handler = ZomatoHandler(self.page, search_request)
            await zomato_handler.initialize()
            zomato_results = await zomato_handler.search_items()
            all_results.extend(zomato_results)
            platform_reports.append(zomato_handler.report)
            await zomato_handler.cleanup()
        except Exception as e:
            logger.error(f"Zomato processing failed: {e}")
            platform_reports.append(PlatformReport(
                platform="Zomato",
                items_found=0,
                successful_additions=0,
                errors=[str(e)]
            ))

        # Calculate discounts
        for result in all_results:
            result.calculate_discount()

        # Find best deal
        best_deal = None
        if all_results:
            valid_results = [r for r in all_results if r.final_price is not None]
            if valid_results:
                best_deal = min(valid_results, key=lambda x: x.final_price)

        execution_time = asyncio.get_event_loop().time() - start_time

        # Create report
        report = RunReport(
            search_request=search_request,
            platforms_processed=[pr.platform for pr in platform_reports],
            total_options=len(all_results),
            best_deal=best_deal,
            platform_reports=platform_reports,
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
                        result.restaurant_name[:30],
                        result.item_name[:30],
                        f"₹{result.final_price}" if result.final_price else "N/A",
                        f"{result.rating}⭐" if result.rating else "N/A"
                    )

            console.print(table)

        # Errors
        for pr in report.platform_reports:
            if pr.errors:
                console.print(f"\n[yellow]⚠️  {pr.platform} Errors:[/yellow]")
                for error in pr.errors[:5]:  # Show first 5 errors
                    console.print(f"  - {error}")
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


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Food Delivery Comparison Agent - Compare deals across Swiggy and Zomato",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Interactive mode:
    python food_delivery_agent.py --interactive
  
  Using config file:
    python food_delivery_agent.py --config config.json
  
  Quick search:
    python food_delivery_agent.py --items "pizza,burger" --rating 4.0
  
  With output file:
    python food_delivery_agent.py --interactive --output results.json
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