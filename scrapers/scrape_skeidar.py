"""
Scraper Skeidar sofa-kategori via innebygd JSON i HTML.
Henter alle produkter, lagrer til CSV.
"""
from playwright.sync_api import sync_playwright
import json
import re
import csv
import time

BASE_URL = "https://www.skeidar.no/alle-produkter/alle-sofaer/sofa/"
MAX_PAGES = None  # sett til None for å hente ALT, eller f.eks. 5 for å teste

def extract_category_data(html: str) -> dict | None:
    """Trekker ut CATEGORY_DATA JSON-objektet fra HTML-en."""
    # Vi leter etter: var CATEGORY_DATA = { ... };
    match = re.search(r'var CATEGORY_DATA\s*=\s*(\{.*?\});\s*var MENU_DATA', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  JSON parse-feil: {e}")
        return None

def scrape_page(page, page_num: int) -> tuple[list, int]:
    """Henter én side med produkter. Returnerer (produkter, totalCount)."""
    url = f"{BASE_URL}?page={page_num}" if page_num > 1 else BASE_URL
    print(f"Henter side {page_num}: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    html = page.content()
    data = extract_category_data(html)
    if not data:
        print(f"  Fant ikke CATEGORY_DATA på side {page_num}")
        return [], 0

    products = data.get("productViewModels", [])
    total = data.get("formModel", {}).get("totalCount", 0)
    print(f"  → {len(products)} produkter funnet (total i kategorien: {total})")
    return products, total

def flatten_product(p: dict) -> dict:
    """Plukker ut feltene vi bryr oss om."""
    info = {}
    try:
        info = json.loads(p.get("informationJson", "{}"))
    except json.JSONDecodeError:
        pass

    return {
        "varenummer": p.get("itemNumber"),
        "navn": p.get("displayName"),
        "variant": p.get("variant"),
        "leverandor": p.get("brand") or info.get("Brand", ""),
        "kategori": p.get("category"),
        "nåpris": p.get("price", {}).get("adjustedPriceWithoutCurrency"),
        "førpris": p.get("price", {}).get("basePriceWithoutCurrency"),
        "rabatt_prosent": p.get("discountPercentage"),
        "ean": info.get("Barcode", ""),
        "lev_varenummer": info.get("Varenummer", ""),
        "url": f"https://www.skeidar.no{p.get('url', '')}",
        "kampanje": p.get("isInPromotion"),
        "antall_varianter": p.get("variantSelectorTotalCount", 0),
    }

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            locale="nb-NO"
        )
        page = context.new_page()

        all_products = []
        page_num = 1
        total_in_category = None

        while True:
            products, total = scrape_page(page, page_num)
            if not products:
                break
            all_products.extend(products)
            if total_in_category is None:
                total_in_category = total

            # Stopp hvis vi har hentet alt eller nådd MAX_PAGES
            if MAX_PAGES and page_num >= MAX_PAGES:
                print(f"\nStopper på MAX_PAGES={MAX_PAGES}")
                break
            if len(all_products) >= total_in_category:
                print(f"\nHar hentet alle {total_in_category} produkter")
                break

            page_num += 1
            time.sleep(1.5)  # vennlig forsinkelse mellom sider

        browser.close()

    # Skriv til CSV
    if all_products:
        flat = [flatten_product(p) for p in all_products]
        fieldnames = list(flat[0].keys())
        with open("skeidar_sofa.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat)

        print(f"\n✓ Skrev {len(flat)} produkter til skeidar_sofa.csv")

        # Rask sanity-sjekk
        with_ean = sum(1 for p in flat if p["ean"])
        with_brand = sum(1 for p in flat if p["leverandor"])
        print(f"  Med EAN: {with_ean} ({with_ean/len(flat)*100:.0f}%)")
        print(f"  Med leverandør: {with_brand} ({with_brand/len(flat)*100:.0f}%)")
    else:
        print("Ingen produkter hentet.")

if __name__ == "__main__":
    main()