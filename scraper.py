"""
scraper.py — Web scraping module for FakeShield
Supports: Amazon India, Flipkart, Meesho, Google Shopping
Strategy: requests + BeautifulSoup with rotating headers + fallback handling
"""

import re
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# ─── Rotating User-Agent Pool ─────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

def get_headers(referer=None):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
        **({"Referer": referer} if referer else {}),
    }

def safe_get(url, timeout=12, retries=2, delay=1.5):
    """HTTP GET with retries, random delay, rotating headers."""
    session = requests.Session()
    for attempt in range(retries):
        try:
            time.sleep(delay + random.uniform(0.5, 1.5))
            resp = session.get(url, headers=get_headers(url), timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 403:
                return None  # blocked
            elif resp.status_code == 503:
                time.sleep(3)
                continue
        except requests.RequestException:
            time.sleep(2)
            continue
    return None

def detect_site(url):
    """Identify which site a URL belongs to."""
    domain = urlparse(url).netloc.lower()
    if "amazon.in" in domain or "amazon.com" in domain:
        return "amazon"
    if "flipkart.com" in domain:
        return "flipkart"
    if "meesho.com" in domain:
        return "meesho"
    if "google.com" in domain and "shopping" in url.lower():
        return "google_shopping"
    return "unknown"

# ─── RESULT SCHEMA ────────────────────────────────────────────────────────────
def make_result(success, site, product_name=None, product_category=None,
                reviews=None, error=None, blocked=False):
    return {
        "success": success,
        "site": site,
        "product_name": product_name or "Unknown Product",
        "product_category": product_category or "General",
        "reviews": reviews or [],
        "error": error,
        "blocked": blocked,
        "review_count": len(reviews) if reviews else 0,
    }

# ─── AMAZON SCRAPER ────────────────────────────────────────────────────────────
def scrape_amazon(url):
    """
    Scrapes Amazon product reviews.
    Converts product URL to reviews page URL automatically.
    """
    # Extract ASIN from URL
    asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    if not asin_match:
        return make_result(False, "amazon", error="Could not extract product ID (ASIN) from URL. Make sure it's a valid Amazon product page.")
    asin = asin_match.group(1)

    # First fetch product page to get name
    product_name = "Amazon Product"
    product_category = "Electronics"
    resp = safe_get(url)
    if resp:
        soup = BeautifulSoup(resp.text, "lxml")
        title_el = soup.select_one("#productTitle")
        if title_el:
            product_name = title_el.get_text(strip=True)[:120]
        cat_el = soup.select_one("#wayfinding-breadcrumbs_feature_div li:nth-child(3) a")
        if cat_el:
            product_category = cat_el.get_text(strip=True)

    # Scrape review pages (up to 3 pages = ~30 reviews)
    reviews = []
    base_url = f"https://www.amazon.in/product-reviews/{asin}"

    for page in range(1, 4):
        review_url = f"{base_url}?pageNumber={page}&sortBy=recent"
        resp = safe_get(review_url, referer=url)
        if not resp:
            if page == 1:
                return make_result(False, "amazon", product_name=product_name,
                                   blocked=True,
                                   error="Amazon blocked the request. This is common without proxies. Try using a VPN or ScraperAPI.")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Detect CAPTCHA
        if soup.find("form", {"action": "/errors/validateCaptcha"}):
            return make_result(False, "amazon", product_name=product_name,
                               blocked=True,
                               error="Amazon showed a CAPTCHA. Use a proxy service like ScraperAPI or Bright Data to bypass.")

        review_divs = soup.select("[data-hook='review']")
        if not review_divs:
            break

        for div in review_divs:
            try:
                name_el = div.select_one(".a-profile-name")
                body_el = div.select_one("[data-hook='review-body'] span")
                rating_el = div.select_one("[data-hook='review-star-rating'] .a-icon-alt")
                date_el = div.select_one("[data-hook='review-date']")
                title_el = div.select_one("[data-hook='review-title'] span:not(.a-icon-alt)")

                if not body_el:
                    continue

                reviewer = name_el.get_text(strip=True) if name_el else "Anonymous"
                body = body_el.get_text(strip=True)
                rating_text = rating_el.get_text(strip=True) if rating_el else "3.0"
                rating = int(float(re.search(r'[\d.]+', rating_text).group()))
                date = date_el.get_text(strip=True) if date_el else ""
                title = title_el.get_text(strip=True) if title_el else ""

                reviews.append({
                    "reviewer_name": reviewer,
                    "review_text": f"{title}. {body}".strip(". ") if title else body,
                    "rating": max(1, min(5, rating)),
                    "source_date": date,
                })
            except Exception:
                continue

        if len(reviews) >= 30:
            break

    if not reviews:
        return make_result(False, "amazon", product_name=product_name,
                           error="No reviews found. The product may have no reviews, or Amazon's layout has changed.")

    return make_result(True, "amazon", product_name=product_name,
                       product_category=product_category, reviews=reviews)


# ─── FLIPKART SCRAPER ──────────────────────────────────────────────────────────
def scrape_flipkart(url):
    """
    Scrapes Flipkart product reviews.
    Flipkart is more scraper-friendly than Amazon.
    """
    # Fetch product page first
    resp = safe_get(url)
    if not resp:
        return make_result(False, "flipkart", blocked=True,
                           error="Flipkart blocked the request. Try again in a few minutes.")

    soup = BeautifulSoup(resp.text, "lxml")

    # Product name — multiple possible selectors
    product_name = "Flipkart Product"
    for sel in ["span.B_NuCI", "h1._9E25nV", "h1.yhB1nd", ".x-product-title"]:
        el = soup.select_one(sel)
        if el:
            product_name = el.get_text(strip=True)[:120]
            break

    product_category = "General"
    breadcrumb = soup.select("._1MR4o5 a")
    if len(breadcrumb) >= 2:
        product_category = breadcrumb[-2].get_text(strip=True)

    # Build reviews URL
    # Flipkart review pages: /product-reviews/itm... or append &page=N
    parsed = urlparse(url)
    pid_match = re.search(r'pid=([A-Z0-9]+)', url)

    reviews = []
    # Try direct review page
    review_base = url
    if "/p/" in url:
        review_base = url.split("?")[0]

    for page in range(1, 4):
        page_url = f"{review_base}?pid={pid_match.group(1)}&sortOrder=MOST_RECENT&page={page}" if pid_match else f"{review_base}&page={page}"
        resp = safe_get(page_url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Flipkart review containers — multiple possible class names
        review_blocks = (
            soup.select("div._16PBlm") or
            soup.select("div.col.EPCmJX.Ma1fCG") or
            soup.select("div[class*='_27M-vq']") or
            soup.select("div.t-ZTKy")
        )

        if not review_blocks:
            # Try alternative: look for rating + review text pairs
            review_blocks = soup.select("div._3LWZlK + div")

        for block in review_blocks:
            try:
                # Rating
                rating_el = block.select_one("div._3LWZlK") or block.select_one("span._2_R_DZ")
                rating = 3
                if rating_el:
                    try:
                        rating = int(float(rating_el.get_text(strip=True)[0]))
                    except Exception:
                        pass

                # Reviewer name
                name_el = block.select_one("p._2sc7ZR._2V5EHH") or block.select_one("p._2NsDsF")
                reviewer = name_el.get_text(strip=True) if name_el else "Anonymous"

                # Review title
                title_el = block.select_one("p._2-N8zT") or block.select_one("p.s1Q9rs")
                title = title_el.get_text(strip=True) if title_el else ""

                # Review body
                body_el = (block.select_one("div.t-ZTKy div._6K-7Co") or
                           block.select_one("div.qwjRop") or
                           block.select_one("p.xi-r8K"))
                if not body_el:
                    # fallback: get all text from block, strip noise
                    body = block.get_text(separator=" ", strip=True)
                    body = re.sub(r'\s+', ' ', body)[:500]
                else:
                    body = body_el.get_text(strip=True)

                if len(body) < 5:
                    continue

                full_review = f"{title}. {body}".strip(". ") if title and title not in body else body

                reviews.append({
                    "reviewer_name": reviewer,
                    "review_text": full_review,
                    "rating": max(1, min(5, rating)),
                    "source_date": "",
                })
            except Exception:
                continue

        if len(reviews) >= 30:
            break

    if not reviews:
        return make_result(False, "flipkart", product_name=product_name,
                           error="No reviews found on this Flipkart page. Try opening the product page directly and copying the full URL including all query parameters.")

    return make_result(True, "flipkart", product_name=product_name,
                       product_category=product_category, reviews=reviews)


# ─── MEESHO SCRAPER ────────────────────────────────────────────────────────────
def scrape_meesho(url):
    """
    Scrapes Meesho product reviews.
    Meesho uses a React frontend — we try to hit their internal API.
    """
    # Extract product ID from URL  e.g. /product-detail/123456789
    pid_match = re.search(r'/(?:product-detail|p)/(\d+)', url)
    if not pid_match:
        return make_result(False, "meesho",
                           error="Could not extract product ID from Meesho URL. Make sure it's a valid product page URL.")
    product_id = pid_match.group(1)

    # Try Meesho internal API (discovered via browser DevTools)
    api_url = f"https://meesho.com/api/v1/products/{product_id}/reviews?page=1&pageSize=20"
    headers = {
        **get_headers(url),
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    # First try the API
    reviews = []
    product_name = "Meesho Product"
    product_category = "Fashion"

    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            product_name = data.get("productName", product_name)
            for r in data.get("reviews", []):
                reviews.append({
                    "reviewer_name": r.get("userName", "Anonymous"),
                    "review_text": r.get("reviewText", ""),
                    "rating": int(r.get("rating", 3)),
                    "source_date": r.get("createdAt", ""),
                })
    except Exception:
        pass

    # Fallback: scrape HTML page
    if not reviews:
        resp = safe_get(url)
        if not resp:
            return make_result(False, "meesho", blocked=True,
                               error="Meesho blocked the request. Meesho heavily uses JavaScript rendering — consider using Selenium for reliable scraping.")

        soup = BeautifulSoup(resp.text, "lxml")

        # Product name
        title_el = soup.select_one("h1") or soup.select_one("[class*='ProductTitle']")
        if title_el:
            product_name = title_el.get_text(strip=True)[:120]

        # Review containers
        review_containers = (
            soup.select("[class*='ReviewCard']") or
            soup.select("[class*='review-card']") or
            soup.select("[class*='Review']")
        )

        for block in review_containers:
            try:
                text = block.get_text(separator=" ", strip=True)
                if len(text) < 10:
                    continue
                # Try to find rating (look for digit 1-5 near a star symbol)
                rating_match = re.search(r'\b([1-5])\b', text[:20])
                rating = int(rating_match.group(1)) if rating_match else 3

                reviews.append({
                    "reviewer_name": "Meesho User",
                    "review_text": text[:400],
                    "rating": rating,
                    "source_date": "",
                })
            except Exception:
                continue

    if not reviews:
        return make_result(False, "meesho", product_name=product_name,
                           error="Meesho uses a JavaScript-heavy frontend. Install Selenium + ChromeDriver for full support: pip install selenium webdriver-manager")

    return make_result(True, "meesho", product_name=product_name,
                       product_category=product_category, reviews=reviews)


# ─── GOOGLE SHOPPING SCRAPER ────────────────────────────────────────────────────
def scrape_google_shopping(url):
    """
    Scrapes Google Shopping product reviews.
    Note: Google aggressively blocks scrapers. Results may vary.
    """
    resp = safe_get(url)
    if not resp:
        return make_result(False, "google_shopping", blocked=True,
                           error="Google blocked the scraping request. Google Shopping requires either official API access or a paid proxy service.")

    soup = BeautifulSoup(resp.text, "lxml")

    # Detect block
    if "detected unusual traffic" in resp.text.lower() or "captcha" in resp.text.lower():
        return make_result(False, "google_shopping", blocked=True,
                           error="Google detected bot activity and showed a CAPTCHA. Use the Google Shopping API or SerpAPI for reliable access.")

    product_name = "Google Shopping Product"
    title_el = soup.select_one("h1") or soup.select_one("[class*='product-title']")
    if title_el:
        product_name = title_el.get_text(strip=True)[:120]

    reviews = []
    # Google Shopping review selectors
    for block in soup.select("[class*='review'], [class*='Review'], [data-review], [class*='UzThIf']"):
        try:
            text = block.get_text(separator=" ", strip=True)
            if len(text) < 15:
                continue
            rating_match = re.search(r'(\d(?:\.\d)?)\s*(?:out of 5|stars?|★)', text, re.IGNORECASE)
            rating = round(float(rating_match.group(1))) if rating_match else 3

            reviews.append({
                "reviewer_name": "Google Shopper",
                "review_text": text[:400],
                "rating": max(1, min(5, rating)),
                "source_date": "",
            })
        except Exception:
            continue

    if not reviews:
        return make_result(False, "google_shopping", product_name=product_name,
                           error="No reviews found. Google Shopping pages are highly dynamic. For reliable results, use the SerpAPI Google Shopping endpoint.")

    return make_result(True, "google_shopping", product_name=product_name,
                       product_category="General", reviews=reviews)


# ─── MAIN ENTRY POINT ─────────────────────────────────────────────────────────
def scrape_product_reviews(url):
    """
    Main function called by Flask routes.
    Auto-detects site and routes to correct scraper.
    Returns a standardised result dict.
    """
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    site = detect_site(url)

    scrapers = {
        "amazon": scrape_amazon,
        "flipkart": scrape_flipkart,
        "meesho": scrape_meesho,
        "google_shopping": scrape_google_shopping,
    }

    if site not in scrapers:
        return make_result(
            False, site,
            error=f"Unsupported website. FakeShield currently supports: Amazon India, Flipkart, Meesho, and Google Shopping. "
                  f"The URL you entered appears to be from '{urlparse(url).netloc}'."
        )

    return scrapers[site](url)
