# Food Delivery Comparison Agent

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/playwright-1.40+-green.svg)](https://playwright.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent, CAP-theorem-aware automation agent that compares food delivery options across **Swiggy** and **Zomato**, finds the best deals, and automatically manages cart operations with consistency guarantees.


##  Overview

This project implements an autonomous web automation agent that:
1. **Searches** for food items across multiple delivery platforms in parallel
2. **Compares** prices, ratings, and deals
3. **Identifies** the best value option
4. **Manages** cart operations with strong consistency guarantees
5. **Persists** browser sessions for seamless user experience

### Why This Project?

- **Time-saving**: Automates the tedious process of comparing food delivery options
- **Best deals**: Automatically finds the lowest prices with good ratings
- **CAP-aware**: Implements distributed systems principles for reliability
- **Production-ready**: Includes retry logic, error handling, and logging

---

## Features

### Core Capabilities
- 1 **Multi-platform Search**: Parallel searches across Swiggy & Zomato
- 2 **Intelligent Filtering**: Price range, minimum ratings, max results
- 3 **Best Deal Detection**: Automated comparison and selection
- 4 **Persistent Sessions**: Reuses logged-in browser contexts
- 5 **Consistent Cart Operations**: Idempotent adds with verification & rollback
- 6 **Rich Output**: Beautiful terminal output with tables and progress bars

### Advanced Features
- **Retry Mechanisms**: Exponential backoff for transient failures
-  **CAP Theorem Implementation**: 
  - **Availability-first** for searches (parallel execution)
  - **Consistency-first** for cart operations (verification & rollback)
- **Detailed Reporting**: JSON export with execution metrics
- **Session Persistence**: Browser profile storage for login state
- **Multiple Interfaces**: Interactive CLI, config file, or direct arguments

---

##  System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Food Delivery Agent                      │
│                                                             │
│  ┌────────────┐      ┌────────────┐      ┌────────────┐     │
│  │   CLI      │─────▶│   Agent    │─────▶│  Browser   │    │
│  │ Interface  │      │ Orchestrator│      │  Context   │    │
│  └────────────┘      └────────────┘       └────────────┘    │
│                             │                               │
│                             │                               │
│              ┌──────────────┴──────────────┐                │
│              │                             │                │
│       ┌──────▼──────┐              ┌───────▼──────┐         │
│       │   Swiggy    │              │   Zomato     │         │
│       │   Handler   │              │   Handler    │         │
│       └─────────────┘              └──────────────┘         │
│                                                             │
│       ┌─────────────────────────────────────────┐           │
│       │         CAP Manager                     │           │
│       │  • Parallel search (Availability)       │           │
│       │  • Consistent cart ops (Consistency)    │           │
│       └─────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                      Core Components                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  FoodDeliveryAgent (Orchestrator)                            │
│  ├── Browser Context Manager                                 │
│  ├── Search Request Validator                                │
│  └── Report Generator                                        │
│                                                              │
│  CAPManager (CAP Theorem Implementation)                     │
│  ├── parallel_search_handlers()                              │
│  │   └── Availability-first: concurrent execution            │
│  └── add_to_cart_consistent()                                │
│      └── Consistency-first: verify + rollback                │
│                                                              │
│  Platform Handlers (Strategy Pattern)                        │
│  ├── BasePlatformHandler (Abstract)                          │
│  │   ├── initialize()                                        │
│  │   ├── search_items()                                      │
│  │   ├── add_item_to_cart()                                  │
│  │   ├── verify_cart_contains()                              │
│  │   └── remove_item_from_cart()                             │
│  │                                                           │
│  ├── SwiggyHandler (Concrete)                                │
│  └── ZomatoHandler (Concrete)                                │
│                                                              │
│  Data Models                                                 │
│  ├── SearchRequest                                           │
│  ├── ItemResult                                              │
│  ├── PlatformReport                                          │
│  └── RunReport                                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites

- **Python**: 3.8 or higher
- **pip**: Latest version
- **OS**: Windows, macOS, or Linux

### Step 1: Clone the Repository

```bash
git clone https://github.com/uayushdubey/Food_Automation.git
cd Food_Automation
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt**:
```
playwright>=1.40.0
rich>=13.0.0
```

### Step 4: Install Playwright Browsers

```bash
playwright install chromium
```

---

## Usage

### 1. Interactive Mode (Recommended for First-Time Users)

```bash
python food_delivery_agent_CAP.py --interactive
```

You'll be prompted to enter:
- Food items (comma-separated)
- Minimum rating filter
- Price range (optional)
- Maximum results per platform
- Location (optional)

### 2. Quick Search Mode

```bash
python food_delivery_agent_CAP.py \
  --items "pizza,burger,biryani" \
  --rating 4.0 \
  --price-max 500 \
  --output results.json
```

### 3. Config File Mode

Create a `config.json`:
```json
{
  "food_items": ["pizza", "burger", "pasta"],
  "min_rating": 4.0,
  "price_min": 100,
  "price_max": 500,
  "max_results_per_platform": 5,
  "location": "Bangalore"
}
```

Run:
```bash
python food_delivery_agent_CAP.py --config config.json --output results.json
```

### 4. Headless Mode (Background Execution)

```bash
python food_delivery_agent_CAP.py \
  --items "biryani" \
  --headless \
  --output results.json
```

---

## ⚙️ Configuration

### Command-Line Arguments

| Argument | Short | Description | Default |
|----------|-------|-------------|---------|
| `--interactive` | `-i` | Interactive mode | - |
| `--config` | `-c` | Config file path | - |
| `--items` | - | Comma-separated food items | - |
| `--rating` | - | Minimum rating filter | 3.8 |
| `--price-min` | - | Minimum price | None |
| `--price-max` | - | Maximum price | None |
| `--max-results` | - | Results per platform | 5 |
| `--location` | - | Delivery location | None |
| `--headless` | - | Run without GUI | False |
| `--slow-mo` | - | Delay between actions (ms) | 100 |
| `--output` | `-o` | Output JSON file | None |
| `--verbose` | `-v` | Verbose logging | False |

### Environment Configuration

Edit the `Config` class in the script:

```python
class Config:
    DEFAULT_TIMEOUT = 15000  # ms
    NAVIGATION_TIMEOUT = 30000  # ms
    RETRY_ATTEMPTS = 3
    RETRY_BACKOFF = 2.0
    MIN_RATING = 3.8
    MAX_RESULTS_PER_PLATFORM = 5
    HEADLESS = False
    SLOW_MO = 100
    USER_DATA_DIR = "./browser_data"  # Persistent profile
```

---

## Design Documentation

## 1. Software Requirements Specification (SRS)

### 1.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Search food items across multiple platforms | High |
| FR-2 | Filter results by rating and price | High |
| FR-3 | Compare and identify best deals | High |
| FR-4 | Add items to cart automatically | Medium |
| FR-5 | Persist browser sessions | Medium |
| FR-6 | Generate detailed reports | Low |
| FR-7 | Export results to JSON | Low |

### 1.2 Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Response time for search | < 30s per platform |
| NFR-2 | Availability | Handle platform downtime gracefully |
| NFR-3 | Consistency | Cart operations must be verifiable |
| NFR-4 | Reliability | Retry failed operations (3 attempts) |
| NFR-5 | Usability | Multiple interfaces (CLI, config) |
| NFR-6 | Maintainability | Modular, extensible architecture |

### 1.3 System Constraints

- **Browser**: Chromium-based (via Playwright)
- **Platforms**: Swiggy, Zomato (extensible)
- **Rate Limiting**: Respect platform rate limits
- **Authentication**: Manual login required (persisted sessions)

---

## 2. High-Level Design (HLD)

### 2.1 System Context

```
┌─────────┐
│  User   │
└────┬────┘
     │
     ▼
┌─────────────────┐       ┌──────────┐
│  Food Agent     │◄─────►│ Swiggy   │
│                 │       └──────────┘
│  • CLI          │
│  • Browser      │       ┌──────────┐
│  • Orchestrator │◄─────►│ Zomato   │
└─────────────────┘       └──────────┘
```

### 2.2 Data Flow Diagram

```
1. User Input
   ↓
2. Validation
   ↓
3. Parallel Search (Availability-First)
   ├── Swiggy Handler ─→ Results A
   └── Zomato Handler ─→ Results B
   ↓
4. Aggregation & Comparison
   ↓
5. Best Deal Selection
   ↓
6. Cart Operation (Consistency-First)
   ├── Add to Cart
   ├── Verify
   └── Rollback (if needed)
   ↓
7. Report Generation
   ↓
8. Output (Terminal + JSON)
```

### 2.3 Component Interaction

```
┌──────────────┐
│   CLI Args   │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────┐
│   FoodDeliveryAgent              │
│   ┌────────────────────────────┐ │
│   │ Browser Context Manager    │ │
│   └────────────┬───────────────┘ │
│                │                 │
│   ┌────────────▼───────────────┐ │
│   │  CAPManager                │ │
│   │  • Parallel Execution      │ │
│   │  • Consistency Guarantees  │ │
│   └────────────┬───────────────┘ │
│                │                 │
│   ┌────────────▼───────────────┐ │
│   │  Platform Handlers         │ │
│   │  ├── SwiggyHandler         │ │
│   │  └── ZomatoHandler         │ │
│   └────────────┬───────────────┘ │
└────────────────┼─────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │  RunReport    │
         └───────────────┘
```

---

## 3. Low-Level Design (LLD)

### 3.1 Class Diagram

```
┌─────────────────────────────┐
│   FoodDeliveryAgent         │
├─────────────────────────────┤
│ - context: BrowserContext   │
│ - page: Page                │
│ - playwright: Playwright    │
├─────────────────────────────┤
│ + initialize()              │
│ + run(SearchRequest)        │
│ + cleanup()                 │
└──────────┬──────────────────┘
           │ uses
           ▼
┌─────────────────────────────┐
│       CAPManager            │
├─────────────────────────────┤
│ - page: Page                │
│ - mode: CAPMode             │
├─────────────────────────────┤
│ + parallel_search_handlers()│
│ + add_to_cart_consistent()  │
│ - _fallback_verify()        │
│ - _fallback_remove()        │
└──────────┬──────────────────┘
           │ manages
           ▼
┌─────────────────────────────┐
│   BasePlatformHandler       │◄──────────┐
├─────────────────────────────┤           │
│ # page: Page                │           │
│ # request: SearchRequest    │           │
│ # report: PlatformReport    │           │
├─────────────────────────────┤           │
│ + initialize()*             │           │
│ + search_items()*           │           │
│ + add_item_to_cart()        │           │
│ + verify_cart_contains()    │           │
│ + remove_item_from_cart()   │           │
└─────────────────────────────┘           │
           △                             │
           │ inherits                     │
           │                              │
  ┌────────┴────────┐                     │
  │                 │                     │
┌─┴────────────┐  ┌─┴────────────┐        │
│SwiggyHandler │  │ZomatoHandler │        │
└──────────────┘  └──────────────┘        │
                                          │
┌─────────────────────────────┐           │
│      Data Models            │           │
├─────────────────────────────┤           │
│ SearchRequest               │───────────┘
│ ItemResult                  │
│ PlatformReport              │
│ RunReport                   │
└─────────────────────────────┘
```

### 3.2 Sequence Diagram: Search Flow

```
User      Agent      CAPMgr     SwiggyH      ZomatoH
 │         │         │          │         │
 │─cmd───▶│          │          │         │
 │         │─init───▶│         │         │
 │         │         │──────parallel──────┐
 │         │         │─init──▶│          │ │
 │         │         │         │◄─────────┘
 │         │         │─init───────────▶│ │
 │         │         │                 │◄┘
 │         │         │                 │
 │         │         │─search────────▶│       
 │         │         │                 │─scrape──┐
 │         │         │                 │◄────────┘
 │         │         │◄results──────── │          
 │        │          │                 │
 │        │          │─search─────────▶│
 │        │          │                 │─scrape─┐
 │        │          │                 │◄───────┘
 │        │          │◄─────results────│
 │        │◄report── │                 │
 │◄output─│          │                 │
```

### 3.3 Sequence Diagram: Consistent Cart Add

```
CAPMgr    Handler    Platform   VerifyAPI
  │         │           │           │
  │─add───▶│           │           │
  │        │──token───▶│           │
  │        │           │◄─ack──────│
  │        │◄──ok──────│            │
  │─verify─────────────────────────▶│
  │                                 │─check cart─┐
  │                                 │◄───────────┘
  │◄──────────────────verified──────│
  │                                 │
  │ [if failed]                     │
  │─rollback──▶│                    │
  │            │──remove───▶│       │
  │            │◄───ok──────│       │
  │◄──done─────│                    │
```

### 3.4 State Machine: Item Processing

```
        ┌─────────┐
        │  START  │
        └────┬────┘
             │
             ▼
      ┌──────────────┐
      │  SEARCHING   │──────timeout────▶ [ERROR]
      └──────┬───────┘
             │ found
             ▼
      ┌──────────────┐
      │  FILTERING   │──────no match───▶ [SKIP]
      └──────┬───────┘
             │ pass
             ▼
      ┌──────────────┐
      │  EXTRACTING  │──────error──────▶ [ERROR]
      └──────┬───────┘
             │ success
             ▼
      ┌──────────────┐
      │   ADDING     │──────failed─────▶ [RETRY]
      └──────┬───────┘
             │ success
             ▼
      ┌──────────────┐
      │  VERIFYING   │──────failed─────▶ [ROLLBACK]
      └──────┬───────┘
             │ verified
             ▼
        ┌─────────┐
        │ SUCCESS │
        └─────────┘
```

### 3.5 Algorithm: Consistent Cart Addition

```python
def add_to_cart_consistent(item, max_attempts=3):
    """
    Guarantees:
    1. Idempotency (no duplicates)
    2. Verification (correct item/price)
    3. Rollback on failure
    """
    token = generate_idempotency_token()
    
    for attempt in range(max_attempts):
        try:
            # Phase 1: Attempt add
            add_item_to_cart(item, token)
            
            # Phase 2: Verify server state
            if verify_cart_contains(item):
                return SUCCESS
            
            # Phase 3: Rollback if verification failed
            remove_item_from_cart(item)
            
            # Exponential backoff
            sleep(backoff ** attempt)
            
        except Exception as e:
            log_error(e)
            continue
    
    return FAILURE
```

### 3.6 Design Patterns Used

| Pattern | Usage | Benefit |
|---------|-------|---------|
| **Strategy** | Platform handlers | Easy addition of new platforms |
| **Template Method** | BasePlatformHandler | Consistent interface |
| **Decorator** | retry_async() | Transparent retry logic |
| **Context Manager** | FoodDeliveryAgent | Resource cleanup |
| **Builder** | SearchRequest | Flexible configuration |
| **Singleton** | Logger | Centralized logging |

---

## 4. CAP Theorem Implementation

### 4.1 Design Decisions

Our system makes different CAP tradeoffs based on operation type:

#### Search Operations: **AP (Availability + Partition Tolerance)**
- **Why**: User experience > strict consistency
- **Implementation**: Parallel execution with timeouts
- **Result**: Fast responses even if one platform is down

```python
# Availability-first: Continue if one platform fails
results = await asyncio.gather(*tasks, return_exceptions=False)
```

#### Cart Operations: **CP (Consistency + Partition Tolerance)**
- **Why**: Cart accuracy > speed
- **Implementation**: Verify + Rollback pattern
- **Result**: No duplicate items, correct prices

```python
# Consistency-first: Verify before confirming
if not verify_cart_contains(item):
    remove_item_from_cart(item)
    retry_or_fail()
```

### 4.2 Failure Handling Matrix

| Scenario | Behavior | User Impact |
|----------|----------|-------------|
| One platform down | Continue with other | Reduced options |
| Cart add fails | Retry + rollback | No duplicate items |
| Verification timeout | Rollback | Safe (no charge) |
| All platforms down | Graceful failure | Clear error message |

---

## 5. Database Design

### 5.1 Data Models (In-Memory)

**SearchRequest**
```
- food_items: List[str]
- min_rating: float
- price_min: Optional[float]
- price_max: Optional[float]
- max_results_per_platform: int
- location: Optional[str]
```

**ItemResult**
```
- restaurant_name: str
- rating: Optional[float]
- item_name: str
- item_price: Optional[float]
- final_price: Optional[float]
- discount_percentage: Optional[float]
- coupon_applied: Optional[str]
- platform: str (enum)
- url: Optional[str]
- timestamp: str (ISO 8601)
```

**PlatformReport**
```
- platform: str
- items_found: int
- successful_additions: int
- errors: List[str]
- results: List[ItemResult]
- available: bool
- latency_ms: Optional[float]
```

**RunReport**
```
- search_request: SearchRequest
- platforms_processed: List[str]
- total_options: int
- best_deal: Optional[ItemResult]
- platform_reports: List[PlatformReport]
- execution_time_seconds: float
- timestamp: str
```

### 5.2 JSON Output Schema

```json
{
  "search_request": {
    "food_items": ["pizza"],
    "min_rating": 4.0,
    "price_min": null,
    "price_max": 500
  },
  "platforms_processed": ["Swiggy", "Zomato"],
  "total_options": 8,
  "best_deal": {
    "restaurant_name": "Pizza Hut",
    "rating": 4.2,
    "item_price": 450,
    "final_price": 380,
    "discount_percentage": 15.56,
    "platform": "Swiggy"
  },
  "platform_reports": [...],
  "execution_time_seconds": 23.45
}
```

---

## 6. API Reference (Internal)

### 6.1 Core Methods

#### `FoodDeliveryAgent.run(SearchRequest) -> RunReport`
Main orchestration method.

**Flow**:
1. Initialize browser
2. Create platform handlers
3. Execute parallel searches
4. Compare results
5. Add best deal to cart
6. Generate report

**Returns**: Complete execution report

---

#### `CAPManager.parallel_search_handlers(handlers, timeout)`
Execute searches with availability-first strategy.

**Parameters**:
- `handlers`: List of platform handlers
- `timeout`: Per-handler timeout (seconds)

**Returns**: Tuple of (results, reports)

---

#### `CAPManager.add_to_cart_consistent(handler, item, max_attempts)`
Add item with consistency guarantees.

**Algorithm**:
1. Generate idempotency token
2. Attempt add operation
3. Verify cart contents
4. Rollback on mismatch
5. Retry with backoff

**Returns**: bool (success/failure)

---

### 6.2 Platform Handler Interface

```python
class BasePlatformHandler:
    async def initialize() -> None:
        """Navigate to platform, check login"""
    
    async def search_items() -> List[ItemResult]:
        """Search and filter items"""
    
    async def add_item_to_cart(item, token) -> None:
        """Add item with idempotency token"""
    
    async def verify_cart_contains(item) -> bool:
        """Verify item in cart"""
    
    async def remove_item_from_cart(item) -> None:
        """Remove item (rollback)"""
```

---

## Troubleshooting

### Common Issues

#### 1. Browser Not Found
```
Error: Executable doesn't exist at ...
```
**Solution**: Install Playwright browsers
```bash
playwright install chromium
```

#### 2. Login Required
```
Warning: Not logged in to Swiggy/Zomato
```
**Solution**: 
1. Run once in non-headless mode
2. Manually log in
3. Session will persist in `./browser_data/`

#### 3. Timeout Errors
```
Error: Timeout waiting for selector
```
**Solution**: Increase timeouts in `Config` class or check internet connection

#### 4. Selector Not Found
```
Error: No element matching selector
```
**Solution**: Website UI changed. Update selectors in platform handlers.

#### 5. Rate Limiting
```
Error: Too many requests
```
**Solution**: Reduce `SLOW_MO` value or add delays

---

## 🤝 Contributing

We welcome contributions! Here's how:

### Development Setup

1. Fork the repository
2. Create a feature branch
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. Make your changes
4. Run tests (manual for now)
5. Commit with descriptive messages
   ```bash
   git commit -m "Add: Support for Uber Eats"
   ```
6. Push to your fork
   ```bash
   git push origin feature/amazing-feature
   ```
7. Open a Pull Request

### Adding New Platforms

1. Create new handler class inheriting `BasePlatformHandler`
2. Implement all abstract methods
3. Add platform-specific selectors
4. Test thoroughly
5. Update documentation

**Example**:
```python
class UberEatsHandler(BasePlatformHandler):
    BASE_URL = "https://www.ubereats.com"
    
    async def initialize(self):
        # Implementation
        pass
    
    async def search_items(self):
        # Implementation
        pass
```

### Code Style

- Follow PEP 8
- Use type hints
- Add docstrings
- Keep methods < 50 lines

---


## Acknowledgments

- **Playwright Team**: For the excellent browser automation framework
- **Rich Library**: For beautiful terminal output
- **Open Source Community**: For inspiration and tools

---

## Contact

**Ayush Dubey**
- GitHub: [@uayushdubey](https://github.com/uayushdubey)
- Repository: [Food_Automation](https://github.com/uayushdubey/Food_Automation)

---

## Roadmap

- [ ] Add support for more platforms (Uber Eats, Dunzo)
- [ ] Implement coupon auto-application
- [ ] Add price tracking over time
- [ ] Create web dashboard
- [ ] Add unit test suite
- [ ] Dockerize the application
- [ ] Create REST API wrapper
- [ ] Implement ML-based deal prediction

---

## Performance Metrics

Typical execution times (M1 Mac, 100 Mbps):

| Operation | Time |
|-----------|------|
| Browser init | 2-3s |
| Single platform search | 8-12s |
| Parallel search (both) | 10-15s |
| Cart operation | 3-5s |
| Total (end-to-end) | 20-30s |

---

## Disclaimer

This tool is for educational purposes. Please:
- Respect platform Terms of Service
- Don't abuse rate limits
- Use responsibly
- Don't use for commercial scraping

---

<div align="center">

**⭐ Star this repo if you find it useful! ⭐**

Made with ❤️ by [Ayush Dubey](https://github.com/uayushdubey)

</div>
