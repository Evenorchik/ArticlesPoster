"""
poster.adspower.api_client

Надёжный HTTP-клиент для AdsPower API (start/stop/active + ожидание готовности Selenium).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from poster.settings import ADS_POWER_API_URL, ADS_POWER_API_KEY, get_profile_no


@dataclass(frozen=True)
class AdsPowerActiveInfo:
    """Нормализованный ответ /active."""
    status: str
    ws_selenium: str
    webdriver_path: str
    raw: Dict[str, Any]

    @property
    def ready_for_selenium(self) -> bool:
        return self.status == "Active" and bool(self.ws_selenium) and bool(self.webdriver_path)


class AdsPowerApiClient:
    """Клиент для работы с AdsPower API."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_s: float = 20.0,
    ):
        self.api_url = (api_url or ADS_POWER_API_URL).rstrip("/")
        self.api_key = api_key or ADS_POWER_API_KEY
        self.timeout_s = timeout_s

    # ---------------------------
    # Low-level helpers
    # ---------------------------
    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            resp = requests.get(url, params=params, headers=self._headers(), timeout=self.timeout_s)
            if resp.status_code != 200:
                logging.warning("AdsPower GET %s -> HTTP %s", url, resp.status_code)
                return None
            return resp.json()
        except requests.RequestException as e:
            logging.warning("AdsPower GET %s failed: %s", url, e)
            return None

    def _post_json(self, url: str, *, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            headers = {"Content-Type": "application/json", **self._headers()}
            resp = requests.post(url, json=payload, headers=headers, timeout=max(self.timeout_s, 30.0))
            if resp.status_code != 200:
                logging.warning("AdsPower POST %s -> HTTP %s", url, resp.status_code)
                return None
            return resp.json()
        except requests.RequestException as e:
            logging.warning("AdsPower POST %s failed: %s", url, e)
            return None

    @staticmethod
    def _extract_active_info(data: Optional[Dict[str, Any]]) -> Optional[AdsPowerActiveInfo]:
        if not data:
            return None
        if data.get("code") != 0:
            return None
        d = (data.get("data") or {}) if isinstance(data.get("data"), dict) else {}
        status = str(d.get("status") or "")
        ws = d.get("ws") or {}
        ws_selenium = ""
        if isinstance(ws, dict):
            ws_selenium = str(ws.get("selenium") or "")
        webdriver_path = str(d.get("webdriver") or "")
        return AdsPowerActiveInfo(status=status, ws_selenium=ws_selenium, webdriver_path=webdriver_path, raw=d)

    # ---------------------------
    # Public API
    # ---------------------------
    def get_active(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Совместимость со старым кодом: вернуть dict data (как раньше) или None."""
        profile_no = get_profile_no(profile_id)
        logging.debug("AdsPower: checking active profile_id=%s (no=%s)", profile_id, profile_no)

        endpoint = f"{self.api_url}/api/v2/browser-profile/active"
        js = self._get_json(endpoint, params={"profile_id": profile_id})
        info = self._extract_active_info(js)
        if not info:
            return None
        return info.raw

    def get_active_info(self, profile_id: str) -> Optional[AdsPowerActiveInfo]:
        """Новая версия: вернуть нормализованный объект AdsPowerActiveInfo."""
        endpoint = f"{self.api_url}/api/v2/browser-profile/active"
        js = self._get_json(endpoint, params={"profile_id": profile_id})
        return self._extract_active_info(js)

    def start(self, profile_id: str) -> bool:
        """Запустить профиль."""
        profile_no = get_profile_no(profile_id)
        logging.info("AdsPower: starting profile_id=%s (no=%s)", profile_id, profile_no)

        endpoint = f"{self.api_url}/api/v2/browser-profile/start"
        js = self._post_json(endpoint, payload={"profile_id": profile_id})
        if not js or js.get("code") != 0:
            logging.error("AdsPower: start failed for %s: %s", profile_id, (js or {}).get("msg"))
            return False
        return True

    def stop(self, profile_id: str) -> bool:
        """Остановить профиль."""
        profile_no = get_profile_no(profile_id)
        logging.info("AdsPower: stopping profile_id=%s (no=%s)", profile_id, profile_no)

        endpoint = f"{self.api_url}/api/v2/browser-profile/stop"
        js = self._post_json(endpoint, payload={"profile_id": profile_id})
        if not js or js.get("code") != 0:
            logging.error("AdsPower: stop failed for %s: %s", profile_id, (js or {}).get("msg"))
            return False
        return True

    def wait_active(
        self,
        profile_id: str,
        timeout_s: float = 120.0,
        poll_s: float = 2.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Совместимость: ждать Active + ws.selenium + webdriver и вернуть dict data.
        """
        info = self.wait_active_info(profile_id, timeout_s=timeout_s, poll_s=poll_s)
        return info.raw if info else None

    def wait_active_info(
        self,
        profile_id: str,
        timeout_s: float = 120.0,
        poll_s: float = 2.0,
    ) -> Optional[AdsPowerActiveInfo]:
        """
        Ждать пока профиль станет готовым для Selenium:
        - status == 'Active'
        - ws.selenium есть
        - webdriver есть
        """
        deadline = time.time() + timeout_s
        last_status = None
        while time.time() < deadline:
            info = self.get_active_info(profile_id)
            if info and info.ready_for_selenium:
                return info

            if info:
                if info.status != last_status:
                    logging.info("AdsPower: profile %s status=%s (ws=%s, webdriver=%s)",
                                 profile_id, info.status, bool(info.ws_selenium), bool(info.webdriver_path))
                    last_status = info.status
            time.sleep(poll_s)

        logging.error("AdsPower: timeout waiting active for profile_id=%s", profile_id)
        return None
