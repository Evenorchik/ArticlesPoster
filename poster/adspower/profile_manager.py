"""
Менеджер профилей Ads Power.
"""
import logging
from typing import Optional, Dict
from poster.models import Profile
from poster.settings import get_profile_id, get_profile_no
from poster.adspower.api_client import AdsPowerApiClient
from poster.adspower.selenium_attach import attach_driver, SELENIUM_AVAILABLE
from poster.adspower.tabs import ensure_tag_tab


class ProfileManager:
    """Менеджер для управления профилями Ads Power."""
    
    def __init__(self, api_client: Optional[AdsPowerApiClient] = None):
        self.api_client = api_client or AdsPowerApiClient()
        self.profiles: Dict[int, Profile] = {}
    
    def ensure_ready(self, profile_no: int) -> Optional[Profile]:
        """
        ЕДИНАЯ точка подготовки профиля:
        - если профиль закрыт/не Active: стартуем через API и ждём Active + ws.selenium + webdriver
        - подключаем Selenium к уже запущенному профилю
        - создаём/поддерживаем вкладку-ярлык (tag tab) для стабильного фокуса окна
        """
        if not SELENIUM_AVAILABLE:
            logging.error("Selenium not available! Install with: pip install selenium")
            return None

        if profile_no not in self.profiles:
            profile_id = get_profile_id(profile_no)
            if not profile_id:
                logging.error("Profile No %d not found in PROFILE_MAPPING", profile_no)
                return None
            self.profiles[profile_no] = Profile(profile_no=profile_no, profile_id=profile_id)

        profile = self.profiles[profile_no]

        # Если driver уже жив — просто проверим/восстановим tag tab
        if profile.driver:
            try:
                _ = profile.driver.current_url
                ensure_tag_tab(profile)
                return profile
            except Exception:
                profile.driver = None
                profile.tag_window_handle = None

        # 1) Гарантируем Active + наличие ws.selenium/webdriver
        profile_status = self.api_client.get_active(profile.profile_id)
        ws = (profile_status or {}).get("ws") or {}
        status = (profile_status or {}).get("status")
        selenium_ok = bool(ws.get("selenium"))
        webdriver_ok = bool((profile_status or {}).get("webdriver"))

        if status != "Active" or not selenium_ok or not webdriver_ok:
            logging.info("Profile %d (ID: %s) is not ready/Active, starting via API...", profile_no, profile.profile_id)
            if not self.api_client.start(profile.profile_id):
                return None
            profile_status = self.api_client.wait_active(profile.profile_id, timeout_s=120, poll_s=3.0)
            if not profile_status:
                return None

        # Иногда Active есть, но ws/webdriver приезжают позже
        ws = (profile_status or {}).get("ws") or {}
        selenium_address = ws.get("selenium") or ""
        webdriver_path = (profile_status or {}).get("webdriver") or ""
        if not selenium_address or not webdriver_path:
            profile_status = self.api_client.wait_active(profile.profile_id, timeout_s=60, poll_s=2.0)
            if not profile_status:
                return None
            ws = (profile_status or {}).get("ws") or {}
            selenium_address = ws.get("selenium") or ""
            webdriver_path = (profile_status or {}).get("webdriver") or ""

        if not selenium_address or not webdriver_path:
            logging.error("Missing selenium address or webdriver path for profile %d", profile_no)
            return None

        # 2) Подключаем Selenium к профилю
        driver = attach_driver(selenium_address, webdriver_path)
        if not driver:
            return None

        profile.driver = driver

        # 3) Создаём tag-tab для стабильного поиска/фокуса окна
        ensure_tag_tab(profile)

        logging.info(
            "✓ Profile %d (ID: %s) ready with window_tag: %s",
            profile_no, profile.profile_id, profile.window_tag
        )
        return profile
    
    def get(self, profile_no: int) -> Optional[Profile]:
        """Получить профиль по номеру."""
        return self.profiles.get(profile_no)
    
    def close(self, profile_no: int) -> bool:
        """Закрыть профиль."""
        if profile_no not in self.profiles:
            return False
        
        profile = self.profiles[profile_no]
        success = self.api_client.stop(profile.profile_id)
        
        if success:
            if profile.driver:
                try:
                    profile.driver.quit()
                except Exception as e:
                    logging.debug("Error quitting driver for profile %d: %s", profile_no, e)
                profile.driver = None
            profile.medium_window_handle = None
            profile.tag_window_handle = None
        
        return success

