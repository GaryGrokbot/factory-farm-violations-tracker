"""
Scraper for USDA FSIS recall data via openFDA Food Enforcement API.

The FSIS website blocks automated access, so we use the openFDA API
which includes FSIS-regulated meat and poultry recalls.

API docs: https://open.fda.gov/apis/food/enforcement/
"""

import httpx
import logging
import time
from database import get_connection, upsert_violation

logger = logging.getLogger(__name__)

OPENFDA_URL = "https://api.fda.gov/food/enforcement.json"

# Search terms for meat/poultry/livestock products
SEARCH_QUERIES = [
    'product_description:"chicken"',
    'product_description:"beef"',
    'product_description:"pork"',
    'product_description:"turkey"',
    'product_description:"poultry"',
    'product_description:"meat"',
    'product_description:"sausage"',
    'product_description:"ground beef"',
    'reason_for_recall:"FSIS"',
    'reason_for_recall:"salmonella"',
    'reason_for_recall:"E. coli"',
    'reason_for_recall:"listeria"',
]

# Classification to severity mapping
CLASS_SEVERITY = {
    "Class I": "High",      # Dangerous or defective, serious health consequences
    "Class II": "Medium",   # May cause temporary health consequences  
    "Class III": "Low",     # Not likely to cause adverse health consequences
}


def fetch_recalls(search_query: str, limit: int = 100, skip: int = 0) -> list:
    """Fetch food enforcement records from openFDA."""
    try:
        resp = httpx.get(
            OPENFDA_URL,
            params={
                "search": search_query,
                "limit": min(limit, 100),
                "skip": skip,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return []  # No results
        logger.error(f"HTTP error fetching recalls: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch recalls: {e}")
        return []


def recall_to_violation(recall: dict) -> dict:
    """Convert an openFDA recall record to a violation record."""
    firm = recall.get("recalling_firm", "Unknown")
    city = recall.get("city", "")
    state = recall.get("state", "")
    classification = recall.get("classification", "")
    reason = recall.get("reason_for_recall", "")
    product = recall.get("product_description", "")
    quantity = recall.get("product_quantity", "")
    recall_number = recall.get("recall_number", "")
    init_date = recall.get("recall_initiation_date", "")
    distribution = recall.get("distribution_pattern", "")
    voluntary = recall.get("voluntary_mandated", "")

    # Format date from YYYYMMDD to YYYY-MM-DD
    date = None
    if init_date and len(init_date) == 8:
        date = f"{init_date[:4]}-{init_date[4:6]}-{init_date[6:8]}"

    location = ", ".join(filter(None, [city, state]))
    severity = CLASS_SEVERITY.get(classification, "Medium")

    desc_parts = [
        f"Product: {product}" if product else None,
        f"Reason: {reason}" if reason else None,
        f"Quantity: {quantity}" if quantity else None,
        f"Distribution: {distribution}" if distribution else None,
        f"Type: {voluntary}" if voluntary else None,
        f"Classification: {classification}" if classification else None,
    ]
    description = ". ".join(filter(None, desc_parts))

    # Truncate description if too long
    if len(description) > 2000:
        description = description[:1997] + "..."

    return {
        "facility_name": firm,
        "location": location,
        "state": state if len(state) == 2 else None,
        "county": None,
        "latitude": None,
        "longitude": None,
        "violation_type": "Food Safety Recall - Meat/Poultry",
        "date": date,
        "source": "USDA FSIS (via openFDA)",
        "source_id": f"FDA-{recall_number}",
        "description": description,
        "severity": severity,
        "penalty_amount": None,
    }


def scrape_fsis_recalls(max_per_query: int = 500):
    """Main scraper: pull meat/poultry recall data."""
    from database import init_db
    init_db()
    conn = get_connection()

    total_inserted = 0
    seen_ids = set()

    for query in SEARCH_QUERIES:
        logger.info(f"Fetching recalls for: {query}")
        skip = 0

        while skip < max_per_query:
            results = fetch_recalls(query, limit=100, skip=skip)
            if not results:
                break

            for recall in results:
                recall_num = recall.get("recall_number", "")
                if recall_num in seen_ids:
                    continue
                seen_ids.add(recall_num)

                violation = recall_to_violation(recall)
                try:
                    upsert_violation(conn, **violation)
                    total_inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert recall {recall_num}: {e}")

            skip += len(results)
            if len(results) < 100:
                break
            time.sleep(0.3)

        conn.commit()
        time.sleep(0.5)

    conn.close()
    logger.info(f"FSIS recall scrape complete. {total_inserted} recalls inserted/updated.")
    return total_inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = scrape_fsis_recalls()
    print(f"Done. {count} recalls scraped from FSIS/openFDA.")
