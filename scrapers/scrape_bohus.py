"""
Scraper Bohus sofa-kategori via Algolia API.
Henter alle produkter direkte, lagrer til CSV.
"""
import requests
import json
import csv
import time

APP_ID = "8RJC7TCMT6"
API_KEY = "NzYyODEwMDIxMjA5MDY1Mzg0NmVkM2U5ZmQwOTk2N2M1Y2FlNTVmM2NhNDc4YjlhYTBjMjJkYjk4MDdjYjVmYXRhZ0ZpbHRlcnM9JnZhbGlkVW50aWw9MTc4NzY2Mzk2MA=="
INDEX = "default_products"
CATEGORY_ID = "2889"  # Sofa-kategorien

URL = f"https://{APP_ID.lower()}-dsn.algolia.net/1/indexes/*/queries"

HEADERS = {
    "x-algolia-api-key": API_KEY,
    "x-algolia-application-id": APP_ID,
    "Content-Type": "application/json"
}

def fetch_page(page_num: int, category_id: str = CATEGORY_ID) -> dict:
    """Henter én side fra Algolia."""
    body = {
        "requests": [{
            "indexName": INDEX,
            "params": f"filters=categoryIds%3A{category_id}&hitsPerPage=100&page={page_num}"
        }]
    }
    resp = requests.post(URL, headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()["results"][0]

def flatten_product(hit: dict) -> dict:
    """Trekker ut feltene vi trenger."""
    price_data = hit.get("price", {}).get("NOK", {})
    sale_data = hit.get("price_on_sale", {}).get("NOK", {})
    campaign = hit.get("campaign_price_communication") or {}

    nåpris = price_data.get("default", 0)
    førpris = ""

    # Sjekk om produktet er på salg
    if sale_data.get("default") is True:
        # nåpris er allerede kampanjeprisen i price.NOK.default
        # Prøv å hente ordinærpris fra formatert streng
        orig_formatted = price_data.get("default_original_formated", "")
        if orig_formatted:
            # Parse "kr 24 470,00,-" til 24470
            import re
            digits = re.sub(r'[^\d]', '', orig_formatted.split(",")[0])
            if digits:
                førpris = int(digits)
        # Fallback: beregn fra rabatt-prosent
        if not førpris and campaign.get("discount"):
            discount_pct = campaign["discount"]
            if 0 < discount_pct < 100 and nåpris > 0:
                førpris = round(nåpris / (1 - discount_pct / 100))

    return {
        "sku": hit.get("sku", ""),
        "navn": hit.get("product_listing_name", hit.get("name", "")),
        "type": hit.get("product_listing_description", ""),
        "leverandor": hit.get("supplier", ""),
        "merke": hit.get("brand", ""),
        "serie": hit.get("series", ""),
        "kategori": hit.get("composition", ""),
        "nåpris": nåpris,
        "førpris": førpris,
        "farge": hit.get("color", ""),
        "tekstil": hit.get("clothing", ""),
        "bredde_cm": hit.get("width", ""),
        "høyde_cm": hit.get("height", ""),
        "sittehøyde_cm": hit.get("sofas_sitheight", ""),
        "sittedybde_cm": hit.get("sofas_sitdepth", ""),
        "url": hit.get("url", ""),
    }

def main():
    # Hent per underkategori for å omgå Algolia sin 1000-grense
    CATEGORIES = [
        ("3021", "2 seter"),
        ("3024", "3 seter"),
        ("3027", "4 seter"),
        ("3030", "Hjørnesofa"),
        ("6315", "U-sofa"),
        ("3033", "Sofa med sjeselong"),
        ("3039", "Modulsofa"),
        ("3018", "Sovesofa"),
        ("3036", "Daybed"),
        ("3042", "Sofagrupper"),
    ]

    all_hits = []
    seen_skus = set()

    for cat_id, cat_name in CATEGORIES:
        page_num = 0
        cat_hits = 0

        while True:
            print(f"Henter {cat_name} (id:{cat_id}), side {page_num}...")
            result = fetch_page(page_num, cat_id)
            hits = result.get("hits", [])
            total = result.get("nbHits", 0)
            nb_pages = result.get("nbPages", 0)

            # Dedupliser på tvers av kategorier
            for hit in hits:
                sku = hit.get("sku", "")
                if isinstance(sku, list):
                    sku = sku[0] if sku else ""
                if sku not in seen_skus:
                    seen_skus.add(sku)
                    all_hits.append(hit)
                    cat_hits += 1

            print(f"  → {len(hits)} treff (nye: {cat_hits}, totalt i kategori: {total})")

            if page_num >= nb_pages - 1 or not hits:
                break

            page_num += 1
            time.sleep(0.5)

        print(f"  Ferdig med {cat_name}: {cat_hits} unike produkter\n")

    # Skriv CSV
    if all_hits:
        flat = [flatten_product(h) for h in all_hits]
        with open("bohus_sofa.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat[0].keys()))
            writer.writeheader()
            writer.writerows(flat)

        print(f"\n{'='*50}")
        print(f"Skrev {len(flat)} unike produkter til bohus_sofa.csv")

        leverandorer = set(p["merke"] for p in flat if p["merke"])
        print(f"Unike merker: {len(leverandorer)}")
        for lev in sorted(leverandorer):
            count = sum(1 for p in flat if p["merke"] == lev)
            print(f"  {lev}: {count}")
    else:
        print("Ingen produkter hentet.")

if __name__ == "__main__":
    main()