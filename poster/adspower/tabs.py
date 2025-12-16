"""
Управление вкладками браузера (tag-tab, Medium tab).
"""
import time
import logging
from typing import Optional
from poster.models import Profile
from poster.settings import MEDIUM_NEW_STORY_URL


def safe_switch_to(driver, handle: str) -> bool:
    """Безопасно переключиться на window handle (вкладку)."""
    try:
        driver.switch_to.window(handle)
        return True
    except Exception:
        return False


def ensure_tag_tab(profile: Profile) -> bool:
    """
    Гарантирует наличие отдельной вкладки-ярлыка (about:blank) с document.title == profile.window_tag.
    
    Зачем:
    - pygetwindow ищет окно по заголовку активной вкладки. Medium часто меняет title, поэтому держим стабильный tag.
    - Для фокуса окна можно временно активировать tag-вкладку, сфокусировать окно, и вернуть Medium.
    """
    if not getattr(profile, "driver", None):
        return False

    driver = profile.driver
    try:
        handles = list(driver.window_handles or [])
        if not handles:
            return False

        def _try_make_tag(handle: str) -> bool:
            try:
                if not safe_switch_to(driver, handle):
                    return False
                try:
                    driver.get("about:blank")
                except Exception:
                    return False
                try:
                    driver.execute_script("document.title = arguments[0];", profile.window_tag)
                except Exception:
                    return False
                profile.tag_window_handle = driver.current_window_handle
                return True
            except Exception:
                return False

        # 1) Если tag handle уже известен и жив — просто обновим title
        if profile.tag_window_handle and profile.tag_window_handle in handles:
            if _try_make_tag(profile.tag_window_handle):
                return True
            profile.tag_window_handle = None

        # 2) Пробуем любую вкладку, кроме Medium (если известна)
        for h in handles:
            if profile.medium_window_handle and h == profile.medium_window_handle:
                continue
            if _try_make_tag(h):
                return True

        # 3) На крайний случай — текущую вкладку
        try:
            current = driver.current_window_handle
        except Exception:
            current = handles[0]
        return _try_make_tag(current)

    except Exception:
        return False


def find_existing_medium_tab(profile: Profile) -> Optional[str]:
    """Ищет уже открытую вкладку Medium в этом профиле (по URL)."""
    if not getattr(profile, "driver", None):
        return None
    driver = profile.driver
    try:
        for h in driver.window_handles or []:
            try:
                driver.switch_to.window(h)
                url = (driver.current_url or "").lower()
                if "medium.com" in url:
                    return h
            except Exception:
                continue
    except Exception:
        return None
    return None


def find_window_by_tag(profile: Profile) -> Optional[str]:
    """Находит window handle вкладки, где title содержит window_tag."""
    if not profile.driver:
        return None

    try:
        handles = profile.driver.window_handles or []
        if not handles:
            return None

        # 1) Сначала tag-tab, если есть
        if profile.tag_window_handle and profile.tag_window_handle in handles:
            return profile.tag_window_handle

        # 2) Ищем по title
        for h in handles:
            try:
                profile.driver.switch_to.window(h)
                title = profile.driver.title or ""
                if profile.window_tag in title:
                    return h
            except Exception:
                continue

        # 3) Иначе Medium handle
        if profile.medium_window_handle and profile.medium_window_handle in handles:
            return profile.medium_window_handle

        return handles[0]
    except Exception as e:
        logging.error("Error finding window by tag: %s", e)
        return None


def wait_document_ready(driver, timeout_s: int = 30) -> bool:
    """Ждать готовности документа."""
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


class TabManager:
    """Менеджер для управления вкладками браузера."""
    
    def __init__(self):
        from poster.settings import MEDIUM_NEW_STORY_URL
        self.MEDIUM_NEW_STORY_URL = MEDIUM_NEW_STORY_URL
    
    def ensure_medium_tab_open(
        self,
        profile: Profile,
        ui,
        window_manager,
        wait_after_open: float = 15.0
    ) -> bool:
        """
        Гарантирует активную вкладку Medium (new-story) так, чтобы PyAutoGUI мог работать.
        
        Важно:
        - НЕ используем `driver.switch_to.new_window()` и `window.open()` — в AdsPower это
          периодически падает (no such window) и/или блокируется расширениями (LavaMoat).
        - Открываем новую вкладку через PyAutoGUI (Ctrl+T) уже в сфокусированном окне.
        """
        if not profile.driver:
            logging.error("Driver not available for profile %d", profile.profile_no)
            return False

        driver = profile.driver

        try:
            # 1) Стабильный title для поиска окна через pygetwindow
            ensure_tag_tab(profile)

            # 2) Активируем tag-tab (чтобы заголовок окна точно был window_tag) и фокусируем окно
            if profile.tag_window_handle:
                safe_switch_to(driver, profile.tag_window_handle)
                ui.sleep(0.2)

            if not window_manager.focus(profile):
                logging.warning("Failed to focus/maximize window (continuing anyway)...")

            ui.sleep(0.2)

            # 3) Открываем новую вкладку Medium ЧЕРЕЗ PyAutoGUI
            handles_before = set(driver.window_handles or [])

            try:
                # Новая вкладка становится активной
                ui.hotkey('ctrl', 't')
                ui.sleep(0.35)

                # Вставляем URL через буфер (быстрее и надёжнее)
                import pyperclip
                pyperclip.copy(self.MEDIUM_NEW_STORY_URL)
                ui.sleep(0.1)
                ui.hotkey('ctrl', 'l')
                ui.sleep(0.05)
                ui.hotkey('ctrl', 'v')
                ui.sleep(0.05)
                ui.press('enter')
            except Exception as e:
                logging.error("Failed to open Medium tab via PyAutoGUI: %s", e)
                return False

            # 4) Ждём, пока Selenium увидит новую вкладку (handle)
            new_handle = None
            deadline = time.time() + 8.0
            while time.time() < deadline:
                handles_now = list(driver.window_handles or [])
                diff = [h for h in handles_now if h not in handles_before]
                if diff:
                    new_handle = diff[-1]
                    break
                ui.sleep(0.2)

            # 5) Если handle не появился, попробуем найти вкладку Medium по URL
            if not new_handle:
                found = find_existing_medium_tab(profile)
                if found:
                    new_handle = found

            if new_handle:
                safe_switch_to(driver, new_handle)
                profile.medium_window_handle = new_handle
            else:
                # Фоллбек: используем текущую вкладку драйвера
                try:
                    profile.medium_window_handle = driver.current_window_handle
                except Exception:
                    pass

            # 6) Усиливаем: навигация Selenium (если PyAutoGUI открыло что-то не то)
            try:
                driver.get(self.MEDIUM_NEW_STORY_URL)
            except Exception:
                pass

            wait_document_ready(driver, timeout_s=30)
            ui.sleep(0.25)

            # 7) Подмешаем tag в title (иногда помогает, но не полагаемся)
            try:
                driver.execute_script(
                    "document.title = arguments[0] + ' | ' + (document.title || 'Medium');",
                    profile.window_tag
                )
            except Exception:
                pass

            # В этот момент активная вкладка на экране — Medium (мы её только что открывали).
            logging.info(
                "✓ Medium tab ready & active. Handle=%s URL=%s",
                getattr(profile, 'medium_window_handle', None),
                getattr(driver, 'current_url', '')
            )

            logging.info(
                "Waiting %.0f seconds for page to stabilize before starting PyAutoGUI cycle...",
                wait_after_open
            )
            from poster.timing import wait_with_log
            wait_with_log(wait_after_open, "Page load wait", 10.0)
            return True

        except Exception as e:
            logging.error("Failed to open Medium URL: %s", e, exc_info=True)
            return False

