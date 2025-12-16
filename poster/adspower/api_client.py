"""
HTTP клиент для Ads Power API.
"""
import time
import logging
import requests
from typing import Optional, Dict
from poster.settings import ADS_POWER_API_URL, ADS_POWER_API_KEY, get_profile_no


class AdsPowerApiClient:
    """Клиент для работы с Ads Power API."""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or ADS_POWER_API_URL
        self.api_key = api_key or ADS_POWER_API_KEY
    
    def get_active(self, profile_id: str) -> Optional[Dict]:
        """Проверить статус профиля."""
        profile_no = get_profile_no(profile_id)
        logging.debug("Checking status of Ads Power profile ID: %s (No: %s)", profile_id, profile_no)

        endpoint = f"{self.api_url}/api/v2/browser-profile/active"
        params = {"profile_id": profile_id}
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                logging.debug("  HTTP error: %s", response.status_code)
                return None

            data = response.json()
            if data.get("code") != 0:
                logging.debug("  API returned error: %s", data.get("msg", "Unknown error"))
                return None

            profile_data = data.get("data", {}) or {}
            status = profile_data.get("status", "Unknown")
            logging.info("Profile ID %s (No: %s) status: %s", profile_id, profile_no, status)
            return profile_data

        except requests.exceptions.RequestException as e:
            logging.error("✗ Request error checking profile status: %s", e)
            return None
        except Exception as e:
            logging.error("✗ Unexpected error checking profile status: %s", e)
            return None
    
    def start(self, profile_id: str) -> bool:
        """Запустить профиль."""
        endpoint = f"{self.api_url}/api/v2/browser-profile/start"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(endpoint, json={"profile_id": profile_id}, headers=headers, timeout=30)
            if resp.status_code != 200:
                logging.error("Failed to start profile: HTTP %d", resp.status_code)
                return False
            data = resp.json()
            if data.get("code") != 0:
                logging.error("Failed to start profile: %s", data.get("msg", "Unknown error"))
                return False
            return True
        except Exception as e:
            logging.error("Error starting profile: %s", e)
            return False
    
    def stop(self, profile_id: str) -> bool:
        """Остановить профиль."""
        profile_no = get_profile_no(profile_id)
        logging.info("Closing profile ID: %s (No: %s)", profile_id, profile_no)

        endpoint = f"{self.api_url}/api/v2/browser-profile/stop"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"profile_id": profile_id}

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
            if response.status_code != 200:
                logging.error("Failed to close profile %d: HTTP %d", profile_no, response.status_code)
                return False

            data = response.json()
            if data.get("code") != 0:
                logging.error("Failed to close profile %d: %s", profile_no, data.get("msg", "Unknown error"))
                return False

            logging.info("✓ Profile %d (ID: %s) closed successfully", profile_no, profile_id)
            return True
        except Exception as e:
            logging.error("Error closing profile %d: %s", profile_no, e)
            return False
    
    def wait_active(self, profile_id: str, timeout_s: int = 90, poll_s: float = 3.0) -> Optional[Dict]:
        """Ждать, пока профиль станет Active и появятся ws.selenium + webdriver."""
        deadline = time.time() + timeout_s
        last_status = None
        while time.time() < deadline:
            st = self.get_active(profile_id)
            if st:
                last_status = st
                status = st.get("status")
                ws = st.get("ws") or {}
                selenium_addr = ws.get("selenium")
                webdriver_path = st.get("webdriver")
                if status == "Active" and selenium_addr and webdriver_path:
                    return st
            time.sleep(poll_s)
        if last_status:
            logging.error("Profile %s did not become ready in time. Last status=%s", profile_id, last_status.get("status"))
        else:
            logging.error("Profile %s did not become ready in time (no status).", profile_id)
        return None

