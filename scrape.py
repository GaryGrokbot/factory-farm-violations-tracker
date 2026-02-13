#!/usr/bin/env python3
"""Run all scrapers to populate the violations database."""

import logging
import sys
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class ScraperTimeout(Exception):
    pass


def timeout_handler(signum, frame):
    raise ScraperTimeout("Scraper timed out")


def main():
    from database import init_db
    init_db()

    total = 0

    # Step 1: Seed with curated real violation data (always works)
    logger.info("=== Seeding database with documented violations ===")
    from scrapers.seed_data import seed_database
    count = seed_database()
    total += count
    logger.info(f"Seed data: {count} records")

    # Step 2: Try openFDA for FSIS recall data (reliable)
    logger.info("=== Scraping FSIS/openFDA meat & poultry recalls ===")
    try:
        from scrapers.fsis_recalls import scrape_fsis_recalls
        count = scrape_fsis_recalls(max_per_query=100)
        total += count
        logger.info(f"FSIS Recalls: {count} records")
    except Exception as e:
        logger.warning(f"FSIS recall scraper failed (seed data still available): {e}")

    # Step 3: Try EPA ECHO API (slow/flaky - 90s timeout)
    logger.info("=== Scraping EPA ECHO CAFO violations (90s timeout) ===")
    try:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(90)
        from scrapers.epa_echo import scrape_epa_echo
        count = scrape_epa_echo(max_per_sic=100)
        total += count
        logger.info(f"EPA ECHO: {count} records")
        signal.alarm(0)
    except ScraperTimeout:
        logger.warning("EPA ECHO scraper timed out after 90s (seed data still available)")
    except Exception as e:
        logger.warning(f"EPA ECHO scraper failed (seed data still available): {e}")
    finally:
        signal.alarm(0)

    logger.info(f"=== Complete. Total: {total} violation records ===")


if __name__ == "__main__":
    main()
