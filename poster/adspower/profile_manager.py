"""
poster.adspower.profile_manager

Единая точка подготовки профиля:
- гарантировать Active+ws.selenium+webdriver
- attach selenium
- создать tag tab (стабильный title)
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, Optional

from poster.models import Profile
from poster.settings import get_profile_id

from poster.adspower.api_client import AdsPowerApiClient
from poster.adspower.selenium_attach import attach_driver, SELENIUM_AVAILABLE
from poster.adspower.tabs import ensure_tag_tab


class ProfileManager:
    """Менеджер для управления профилями AdsPower (кэширует Profile объекты)."""

    def __init__(self, api_client: Optional[AdsPowerApiClient] = None):
        self.api_client = api_client or AdsPowerApiClient()
        self.profiles: Dict[int, Profile] = {}

    def ensure_ready(self, profile_no: int) -> Optional[Profile]:
        """
        Подготовить профиль: Active + attach selenium + tag tab.
        Возвращает Profile с заполненным driver.
        """
        if not SELENIUM_AVAILABLE:
            logging.error("Selenium not available! Install selenium>=4.")
            return None

        if profile_no not in self.profiles:
            profile_id = get_profile_id(profile_no)
            if not profile_id:
                logging.error("Profile No %d not found in mapping", profile_no)
                return None
            self.profiles[profile_no] = Profile(profile_no=profile_no, profile_id=profile_id)

        profile = self.profiles[profile_no]

        # Убедимся, что window_tag достаточно уникален (если в модели он "простенький")
        try:
            if not getattr(profile, "window_tag", ""):
                profile.window_tag = f"ADS_PROFILE_{profile_no}_{uuid.uuid4().hex[:6]}"
        except Exception:
            pass

        # Если driver уже жив — проверим что он отвечает, и обновим tag tab
        if getattr(profile, "driver", None):
            try:
                _ = profile.driver.window_handles
                ensure_tag_tab(profile)
                return profile
            except Exception:
                try:
                    profile.driver.quit()
                except Exception:
                    pass
                profile.driver = None
                profile.tag_window_handle = None
                profile.medium_window_handle = None

        # 1) Ждём готовности через API
        info = self.api_client.get_active_info(profile.profile_id)
        if not info or not info.ready_for_selenium:
            logging.info("Profile %d (id=%s) not ready, starting...", profile_no, profile.profile_id)
            if not self.api_client.start(profile.profile_id):
                return None
            info = self.api_client.wait_active_info(profile.profile_id, timeout_s=150, poll_s=3.0)
            if not info:
                return None

        # 2) Запомним pid если есть (опционально) – пригодится для WindowManager
        try:
            for k in ("pid", "browser_pid", "process_id"):
                if k in (info.raw or {}) and info.raw.get(k):
                    setattr(profile, "pid", info.raw.get(k))
                    break
        except Exception:
            pass

        selenium_address = info.ws_selenium
        webdriver_path = info.webdriver_path

        # 3) Attach selenium
        driver = attach_driver(selenium_address, webdriver_path)
        if not driver:
            return None

        profile.driver = driver

        # 4) Создаём tag tab – НЕ ломая вкладки
        ensure_tag_tab(profile)

        logging.info("✓ Profile %d ready (id=%s, tag=%s)", profile_no, profile.profile_id, getattr(profile, "window_tag", ""))
        return profile

    def get(self, profile_no: int) -> Optional[Profile]:
        return self.profiles.get(profile_no)

    def close(self, profile_no: int) -> bool:
        """Остановить профиль через API и закрыть driver."""
        profile = self.profiles.get(profile_no)
        if not profile:
            return False

        ok = self.api_client.stop(profile.profile_id)
        if ok and getattr(profile, "driver", None):
            try:
                profile.driver.quit()
            except Exception:
                pass
            profile.driver = None
        profile.medium_window_handle = None
        profile.tag_window_handle = None
        return ok
