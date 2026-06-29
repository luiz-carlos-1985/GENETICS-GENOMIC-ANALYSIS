import requests
import logging
import os

log = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8080")


def update_analysis_status(analysis_id: str, status: str, result_json: str = None):
    """
    Updates the analysis status in the backend database via REST API.
    Status: PROCESSING, COMPLETED, FAILED
    """
    try:
        payload = {
            "status": status,
            "resultJson": result_json
        }
        response = requests.put(
            f"{BACKEND_URL}/api/genomic/analysis/{analysis_id}/status",
            json=payload,
            timeout=10
        )
        if response.status_code == 200:
            log.info("Successfully updated analysis %s to status %s", analysis_id, status)
        else:
            log.error("Failed to update status. HTTP %d: %s", response.status_code, response.text)
    except Exception as e:
        log.error("Error updating analysis status: %s", str(e))
