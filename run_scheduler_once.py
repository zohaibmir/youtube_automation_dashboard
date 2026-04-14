#!/usr/bin/env python3
"""run_scheduler_once.py — Trigger scheduler via API for cron jobs.

Used by Render cron service to trigger the /api/scheduler/run-next endpoint.
This calls the web service API which has access to the persistent disk.
"""

import logging
import os
import sys
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        url = os.getenv("RENDER_EXTERNAL_URL", "https://youtube-automation-19fr.onrender.com")
        username = os.getenv("DASHBOARD_USERNAME", "")
        password = os.getenv("DASHBOARD_PASSWORD", "")
        
        endpoint = f"{url}/api/scheduler/run-next"
        logger.info("=== Cron job: Triggering scheduler via %s ===", endpoint)
        
        response = requests.post(
            endpoint,
            auth=(username, password) if username and password else None,
            timeout=10,
        )
        response.raise_for_status()
        
        result = response.json()
        logger.info("=== Scheduler triggered successfully: %s ===", result)
        sys.exit(0)
    except Exception as exc:
        logger.error("=== Cron job failed: %s ===", exc, exc_info=True)
        sys.exit(1)
