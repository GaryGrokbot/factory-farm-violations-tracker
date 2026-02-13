"""
Scraper for EPA ECHO (Enforcement and Compliance History Online).

Pulls CAFO (Concentrated Animal Feeding Operation) violations from the
Clean Water Act facility search API with proper retry/polling logic.

SIC codes for livestock:
  0211 - Beef Cattle Feedlots
  0213 - Hogs  
  0251 - Broiler/Fryer Chickens
  0252 - Chicken Eggs
  0253 - Turkeys

API docs: https://echo.epa.gov/tools/web-services/facility-search-water
"""

import httpx
import time
import logging
from database import get_connection, upsert_violation

logger = logging.getLogger(__name__)

BASE_URL = "https://echodata.epa.gov/echo"
CAFO_SIC_CODES = ["0211", "0213", "0251", "0252", "0253"]

SIC_NAMES = {
    "0211": "Beef Cattle Feedlots",
    "0213": "Hog Operations",
    "0251": "Broiler/Fryer Chickens",
    "0252": "Egg Production",
    "0253": "Turkey Operations",
}


def fetch_facilities_for_sic(sic_code: str, max_facilities: int = 200) -> list:
    """Fetch CWA facilities for a given SIC code from ECHO with retry/polling."""
    logger.info(f"Querying EPA ECHO for SIC {sic_code} ({SIC_NAMES.get(sic_code, 'Unknown')})...")

    # Step 1: Initiate query
    try:
        resp = httpx.get(
            f"{BASE_URL}/cwa_rest_services.get_facilities",
            params={"output": "JSON", "p_sic": sic_code, "p_qiv": "V", "responseset": 0},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Failed initial query for SIC {sic_code}: {e}")
        return []

    results = data.get("Results", {})
    
    # Handle "Working" status with polling
    poll_attempts = 0
    while results.get("Message") == "Working" and poll_attempts < 12:
        poll_attempts += 1
        logger.info(f"  API processing (attempt {poll_attempts}/12), waiting 5s...")
        time.sleep(5)
        try:
            resp = httpx.get(
                f"{BASE_URL}/cwa_rest_services.get_facilities",
                params={"output": "JSON", "p_sic": sic_code, "p_qiv": "V", "responseset": 0},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("Results", {})
        except Exception as e:
            logger.warning(f"  Poll attempt {poll_attempts} failed: {e}")
            continue

    total_rows = int(results.get("QueryRows", 0))
    qid = results.get("QueryID")

    if total_rows == 0 or not qid:
        logger.info(f"  No facilities found for SIC {sic_code}")
        return []

    logger.info(f"  Found {total_rows} facilities, fetching up to {max_facilities}...")

    # Step 2: Fetch pages using QID with retry
    all_facilities = []
    pages_to_fetch = (min(total_rows, max_facilities) + 99) // 100

    for page in range(1, pages_to_fetch + 1):
        for attempt in range(6):  # Up to 6 attempts with 5s waits
            try:
                resp = httpx.get(
                    f"{BASE_URL}/cwa_rest_services.get_qid",
                    params={"qid": qid, "output": "JSON", "responseset": page, "pagesize": 100},
                    timeout=60,
                )
                resp.raise_for_status()
                page_data = resp.json()
                page_results = page_data.get("Results", {})
                
                # Check for "Working" status
                if page_results.get("Message") == "Working":
                    logger.info(f"  Page {page} still processing (attempt {attempt+1}/6), waiting 5s...")
                    time.sleep(5)
                    continue
                
                facilities = page_results.get("Facilities", [])
                if facilities:
                    all_facilities.extend(facilities)
                break
            except Exception as e:
                logger.warning(f"  Page {page} attempt {attempt+1} failed: {e}")
                time.sleep(3)
        
        time.sleep(1)

    logger.info(f"  Fetched {len(all_facilities)} facilities for SIC {sic_code}")
    return all_facilities[:max_facilities]


def facility_to_violation(facility: dict, sic_code: str) -> dict | None:
    """Convert an ECHO facility record into a violation record."""
    name = facility.get("CWPName", "Unknown")
    source_id = facility.get("SourceID", "")
    street = facility.get("CWPStreet", "")
    city = facility.get("CWPCity", "")
    state = facility.get("CWPState", "")
    county = facility.get("CWPCounty", "")
    lat = facility.get("FacLat")
    lon = facility.get("FacLong")
    compliance_status = facility.get("CWPComplianceStatus", "")
    snc_status = facility.get("CWPSNCStatus", "")
    qtrs_nc = facility.get("CWPQtrsWithNC", "0")
    permit_status = facility.get("CWPPermitStatusDesc", "")
    last_inspection = facility.get("CWPDateLastInspection", "")
    last_penalty_date = facility.get("CWPDateLastPenalty", "")
    total_penalties = facility.get("CWPTotalPenalties", "")
    formal_ea_count = facility.get("CWPFormalEaCount", "0")

    location = ", ".join(filter(None, [street, city, state]))

    try:
        lat = float(lat) if lat else None
        lon = float(lon) if lon else None
    except (ValueError, TypeError):
        lat = lon = None

    severity = "Low"
    if snc_status and "S" in str(snc_status).upper():
        severity = "High"
    elif compliance_status and "violation" in str(compliance_status).lower():
        severity = "Medium"

    try:
        qtrs = int(qtrs_nc) if qtrs_nc else 0
    except ValueError:
        qtrs = 0

    if qtrs == 0 and severity == "Low" and not last_penalty_date:
        return None

    desc_parts = [
        f"CAFO Type: {SIC_NAMES.get(sic_code, sic_code)}",
        f"Permit Status: {permit_status}" if permit_status else None,
        f"Compliance: {compliance_status}" if compliance_status else None,
        f"Quarters in Non-Compliance: {qtrs}" if qtrs > 0 else None,
        f"Formal Enforcement Actions: {formal_ea_count}" if formal_ea_count and formal_ea_count != "0" else None,
    ]
    description = ". ".join(filter(None, desc_parts))

    penalty = None
    if total_penalties:
        try:
            penalty = float(str(total_penalties).replace("$", "").replace(",", ""))
        except ValueError:
            pass

    return {
        "facility_name": name,
        "location": location,
        "state": state,
        "county": county,
        "latitude": lat,
        "longitude": lon,
        "violation_type": "Clean Water Act - CAFO",
        "date": last_penalty_date or last_inspection or None,
        "source": "EPA ECHO",
        "source_id": f"ECHO-CWA-{source_id}",
        "description": description,
        "severity": severity,
        "penalty_amount": penalty,
    }


def scrape_epa_echo(max_per_sic: int = 200):
    """Main scraper: pull CAFO violations from EPA ECHO."""
    from database import init_db
    init_db()
    conn = get_connection()

    total_inserted = 0

    for sic_code in CAFO_SIC_CODES:
        facilities = fetch_facilities_for_sic(sic_code, max_per_sic)

        for facility in facilities:
            v = facility_to_violation(facility, sic_code)
            if v:
                try:
                    upsert_violation(conn, **v)
                    total_inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert: {e}")

        conn.commit()
        logger.info(f"  Committed SIC {sic_code}, total so far: {total_inserted}")
        time.sleep(1)

    conn.close()
    logger.info(f"EPA ECHO scrape complete. {total_inserted} violations inserted/updated.")
    return total_inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = scrape_epa_echo()
    print(f"Done. {count} violations scraped from EPA ECHO.")
