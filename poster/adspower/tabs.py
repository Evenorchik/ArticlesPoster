"""
poster.adspower.tabs

Управление вкладками:
- tag tab (стабильный title/marker, чтобы находить окно)
- вкладка Medium new-story

Ключевой принцип: НИКОГДА не "перезаписывать" существующую вкладку через driver.get("about:blank") на случайном handle.
Tag tab создаётся как отдельная вкладка и маркируется window.name.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Set

from poster.models import Profile
from poster.settings import MEDIUM_NEW_STORY_URL, QUORA_URL


# ---------------------------
# Generic helpers
# ---------------------------
def safe_switch_to(driver, handle: str, retries: int = 3, sleep_s: float = 0.15) -> bool:
    """Безопасно переключиться на вкладку по handle с ретраями."""
    for _ in range(max(1, retries)):
        try:
            driver.switch_to.window(handle)
            return True
        except Exception:
            time.sleep(sleep_s)
    return False


def wait_document_ready(driver, timeout_s: float = 30.0) -> bool:
    """Ждать document.readyState == complete."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            state = driver.execute_script("return document.readyState")
            if state == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def wait_url_contains(driver, needle: str, timeout_s: float = 25.0) -> bool:
    """Ждать пока current_url содержит needle."""
    needle = (needle or "").lower()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            url = (driver.current_url or "").lower()
            if needle in url:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _wait_new_handle(driver, before: Set[str], timeout_s: float = 6.0) -> Optional[str]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            now = list(driver.window_handles or [])
        except Exception:
            now = []
        diff = [h for h in now if h not in before]
        if diff:
            return diff[-1]
        time.sleep(0.15)
    return None


def _create_new_tab(driver) -> Optional[str]:
    """
    Создать новую вкладку максимально надёжно.
    Порядок: CDP Target.createTarget -> switch_to.new_window -> window.open.
    """
    before = set(driver.window_handles or [])

    # 1) CDP (лучший вариант при attach через debuggerAddress)
    try:
        driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank"})
        h = _wait_new_handle(driver, before, timeout_s=6.0)
        if h:
            return h
    except Exception:
        pass

    # 2) Selenium new_window
    try:
        driver.switch_to.new_window("tab")
        return driver.current_window_handle
    except Exception:
        pass

    # 3) JS window.open
    try:
        driver.execute_script("window.open('about:blank', '_blank');")
        h = _wait_new_handle(driver, before, timeout_s=6.0)
        if h:
            return h
    except Exception:
        pass

    return None


# ---------------------------
# Tag tab
# ---------------------------
def _tag_marker(tag: str) -> str:
    return f"__ADSP_TAG__::{tag}"


def ensure_tag_tab(profile: Profile) -> bool:
    """
    Гарантирует наличие отдельной tag-вкладки, помеченной window.name.
    Мы НЕ навигируем никакие чужие вкладки.
    """
    driver = getattr(profile, "driver", None)
    if not driver:
        return False

    try:
        handles = list(driver.window_handles or [])
    except Exception:
        return False
    if not handles:
        return False

    tag = getattr(profile, "window_tag", "") or ""
    marker = _tag_marker(tag)

    # 0) Если tag handle уже есть и жив — проверим marker и обновим title
    existing = getattr(profile, "tag_window_handle", None)
    if existing and existing in handles and safe_switch_to(driver, existing):
        try:
            name = driver.execute_script("return window.name || ''")
        except Exception:
            name = ""

        if name == marker:
            try:
                driver.execute_script("document.title = arguments[0];", tag)
            except Exception:
                pass
            profile.tag_window_handle = driver.current_window_handle
            return True

        # Если marker не совпал — НЕ трогаем эту вкладку (это не наш tag tab)
        profile.tag_window_handle = None

    # 1) Создаём отдельную вкладку
    new_handle = _create_new_tab(driver)
    if not new_handle:
        return False
    if not safe_switch_to(driver, new_handle):
        return False

    # 2) Маркируем + ставим title (без навигации)
    try:
        driver.execute_script(
            "window.name = arguments[0]; document.title = arguments[1];",
            marker,
            tag,
        )
    except Exception:
        return False

    profile.tag_window_handle = new_handle
    return True


# ---------------------------
# Medium tab
# ---------------------------
def find_existing_medium_tab(profile: Profile) -> Optional[str]:
    """Ищет вкладку Medium, предпочитая /new-story."""
    driver = getattr(profile, "driver", None)
    if not driver:
        return None

    try:
        handles = list(driver.window_handles or [])
    except Exception:
        return None

    best = None
    fallback = None
    for h in handles:
        if not safe_switch_to(driver, h):
            continue
        try:
            url = (driver.current_url or "").lower()
        except Exception:
            continue

        if "medium.com/new-story" in url:
            best = h
            break
        if "medium.com" in url and not fallback:
            fallback = h

    return best or fallback


def find_window_by_tag(profile: Profile) -> Optional[str]:
    """
    Находит handle вкладки, которую можно безопасно сделать активной для фокуса окна:
    - сначала tag tab
    - затем вкладка где title содержит window_tag
    - затем medium handle
    - затем первая вкладка
    """
    driver = getattr(profile, "driver", None)
    if not driver:
        return None

    try:
        handles = list(driver.window_handles or [])
    except Exception:
        return None
    if not handles:
        return None

    if getattr(profile, "tag_window_handle", None) in handles:
        return profile.tag_window_handle

    tag = getattr(profile, "window_tag", "") or ""
    for h in handles:
        if not safe_switch_to(driver, h):
            continue
        try:
            title = driver.title or ""
        except Exception:
            title = ""
        if tag and tag in title:
            return h

    if getattr(profile, "medium_window_handle", None) in handles:
        return profile.medium_window_handle

    return handles[0]


class TabManager:
    """
    Менеджер вкладок. По возможности работает чисто через Selenium/CDP.
    UI (pyautogui) используется только как fallback, если создание вкладки Selenium/CDP не сработало.
    """

    def __init__(self, medium_new_story_url: str = MEDIUM_NEW_STORY_URL, quora_url: str = QUORA_URL):
        self.MEDIUM_NEW_STORY_URL = medium_new_story_url
        self.QUORA_URL = quora_url

    def ensure_medium_tab_open(
        self,
        profile: Profile,
        ui=None,
        window_manager=None,
        wait_after_open: float = 1.5,
    ) -> bool:
        """
        Гарантирует, что:
        - существует вкладка Medium /new-story
        - она активна
        - окно (опционально) вынесено на передний план и максимизировано (для PyAutoGUI)
        """
        driver = getattr(profile, "driver", None)
        if not driver:
            logging.error("TabManager: no driver for profile %s", getattr(profile, "profile_no", "?"))
            return False

        # 1) Подготовим tag tab (не ломая вкладки)
        ensure_tag_tab(profile)

        # 2) Пытаемся найти уже открытую Medium вкладку
        h = find_existing_medium_tab(profile)
        if h:
            safe_switch_to(driver, h)
            profile.medium_window_handle = h
        else:
            # 3) Создаём новую вкладку под Medium
            created = _create_new_tab(driver)
            if created:
                safe_switch_to(driver, created)
                try:
                    driver.get(self.MEDIUM_NEW_STORY_URL)
                except Exception:
                    pass
                wait_document_ready(driver, timeout_s=30)
                wait_url_contains(driver, "medium.com", timeout_s=20)
                profile.medium_window_handle = created
            else:
                # 4) Fallback на UI
                if not (ui and window_manager):
                    logging.error("TabManager: cannot create tab via Selenium/CDP and no UI fallback provided")
                    return False

                # сделаем tag активным -> фокус -> ctrl+t -> URL
                if getattr(profile, "tag_window_handle", None):
                    safe_switch_to(driver, profile.tag_window_handle)
                    time.sleep(0.2)

                try:
                    window_manager.focus(profile)
                except Exception:
                    pass

                handles_before = set(driver.window_handles or [])
                try:
                    ui.hotkey("ctrl", "t")
                    ui.sleep(0.35)
                    ui.hotkey("ctrl", "l")
                    ui.sleep(0.05)
                    if hasattr(ui, "paste_text"):
                        ui.paste_text(self.MEDIUM_NEW_STORY_URL)
                    else:
                        ui.write(self.MEDIUM_NEW_STORY_URL)
                    ui.sleep(0.05)
                    ui.press("enter")
                except Exception as e:
                    logging.error("TabManager UI fallback failed: %s", e)
                    return False

                new_h = _wait_new_handle(driver, handles_before, timeout_s=8.0)
                if new_h:
                    safe_switch_to(driver, new_h)
                    profile.medium_window_handle = new_h
                else:
                    h2 = find_existing_medium_tab(profile)
                    if h2:
                        safe_switch_to(driver, h2)
                        profile.medium_window_handle = h2
                    else:
                        profile.medium_window_handle = driver.current_window_handle

                # Усилим навигацию Selenium
                try:
                    driver.get(self.MEDIUM_NEW_STORY_URL)
                except Exception:
                    pass
                wait_document_ready(driver, timeout_s=30)
                wait_url_contains(driver, "medium.com", timeout_s=20)

        # 5) Верификация: мы реально на /new-story (а не снова about:blank)
        if getattr(profile, "medium_window_handle", None):
            safe_switch_to(driver, profile.medium_window_handle)

        if not wait_url_contains(driver, "medium.com/new-story", timeout_s=15.0):
            # Попробуем мягко восстановиться (не трогая другие вкладки)
            try:
                driver.get(self.MEDIUM_NEW_STORY_URL)
            except Exception:
                pass
            wait_document_ready(driver, timeout_s=30)
            wait_url_contains(driver, "medium.com/new-story", timeout_s=20)

        # 6) Теперь можно фокусировать/максимизировать окно под PyAutoGUI
        if window_manager:
            try:
                # Для поиска HWND по title (если используется fallback) полезно сделать tag активным
                if getattr(profile, "tag_window_handle", None):
                    safe_switch_to(driver, profile.tag_window_handle)
                    time.sleep(0.15)
                window_manager.focus(profile)
            except Exception:
                pass

        # 7) Вернёмся на Medium
        if getattr(profile, "medium_window_handle", None):
            safe_switch_to(driver, profile.medium_window_handle)

        time.sleep(max(0.0, float(wait_after_open)))
        return True

    def ensure_quora_tab_open(
        self,
        profile: Profile,
        ui=None,
        window_manager=None,
        wait_after_open: float = 1.5,
    ) -> bool:
        """
        Гарантирует, что:
        - существует вкладка Quora
        - она активна
        - окно (опционально) вынесено на передний план и максимизировано (для PyAutoGUI)
        """
        driver = getattr(profile, "driver", None)
        if not driver:
            logging.error("TabManager: no driver for profile %s", getattr(profile, "profile_no", "?"))
            return False

        # 1) Подготовим tag tab (не ломая вкладки)
        ensure_tag_tab(profile)

        # 2) Пытаемся найти уже открытую Quora вкладку
        h = None
        try:
            handles = list(driver.window_handles or [])
            for handle in handles:
                if not safe_switch_to(driver, handle):
                    continue
                try:
                    url = driver.current_url
                    if 'quora.com' in url:
                        h = handle
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if h:
            safe_switch_to(driver, h)
            profile.quora_window_handle = h
        else:
            # 3) Создаём новую вкладку под Quora
            created = _create_new_tab(driver)
            if created:
                safe_switch_to(driver, created)
                try:
                    driver.get(self.QUORA_URL)
                except Exception:
                    pass
                wait_document_ready(driver, timeout_s=30)
                wait_url_contains(driver, "quora.com", timeout_s=20)
                profile.quora_window_handle = created
            else:
                # 4) Fallback на UI
                if not (ui and window_manager):
                    logging.error("TabManager: cannot create tab via Selenium/CDP and no UI fallback provided")
                    return False

                # сделаем tag активным -> фокус -> ctrl+t -> URL
                if getattr(profile, "tag_window_handle", None):
                    safe_switch_to(driver, profile.tag_window_handle)
                    time.sleep(0.2)

                try:
                    window_manager.focus(profile)
                except Exception:
                    pass

                handles_before = set(driver.window_handles or [])
                try:
                    ui.hotkey("ctrl", "t")
                    ui.sleep(0.35)
                    ui.hotkey("ctrl", "l")
                    ui.sleep(0.05)
                    if hasattr(ui, "paste_text"):
                        ui.paste_text(self.QUORA_URL)
                    else:
                        ui.write(self.QUORA_URL)
                    ui.sleep(0.05)
                    ui.press("enter")
                except Exception as e:
                    logging.error("TabManager UI fallback failed: %s", e)
                    return False

                new_h = _wait_new_handle(driver, handles_before, timeout_s=8.0)
                if new_h:
                    safe_switch_to(driver, new_h)
                    profile.quora_window_handle = new_h
                else:
                    # Ищем существующую Quora вкладку
                    try:
                        handles = list(driver.window_handles or [])
                        for handle in handles:
                            if not safe_switch_to(driver, handle):
                                continue
                            try:
                                url = driver.current_url
                                if 'quora.com' in url:
                                    profile.quora_window_handle = handle
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass
                    
                    if not getattr(profile, "quora_window_handle", None):
                        profile.quora_window_handle = driver.current_window_handle

                # Усилим навигацию Selenium
                try:
                    driver.get(self.QUORA_URL)
                except Exception:
                    pass
                wait_document_ready(driver, timeout_s=30)
                wait_url_contains(driver, "quora.com", timeout_s=20)

        # 5) Верификация: мы реально на quora.com
        if getattr(profile, "quora_window_handle", None):
            safe_switch_to(driver, profile.quora_window_handle)

        if not wait_url_contains(driver, "quora.com", timeout_s=15.0):
            # Попробуем мягко восстановиться (не трогая другие вкладки)
            try:
                driver.get(self.QUORA_URL)
            except Exception:
                pass
            wait_document_ready(driver, timeout_s=30)
            wait_url_contains(driver, "quora.com", timeout_s=20)

        # 6) Теперь можно фокусировать/максимизировать окно под PyAutoGUI
        if window_manager:
            try:
                # Для поиска HWND по title (если используется fallback) полезно сделать tag активным
                if getattr(profile, "tag_window_handle", None):
                    safe_switch_to(driver, profile.tag_window_handle)
                    time.sleep(0.15)
                window_manager.focus(profile)
            except Exception:
                pass

        # 7) Вернёмся на Quora
        if getattr(profile, "quora_window_handle", None):
            safe_switch_to(driver, profile.quora_window_handle)

        time.sleep(max(0.0, float(wait_after_open)))
        return True
