"""
Управление окнами ОС через pygetwindow.
"""
import time
import logging
from typing import Optional
from poster.models import Profile


class WindowManager:
    """Менеджер для работы с окнами браузера через pygetwindow."""
    
    def __init__(self):
        try:
            import pygetwindow as gw
            self.gw = gw
            self._available = True
        except ImportError:
            self._available = False
            logging.error("pygetwindow not available")
    
    def focus(self, profile: Profile) -> bool:
        """Безопасно фокусирует и максимизирует окно профиля."""
        if not self._available:
            return False
        
        from poster.adspower.tabs import ensure_tag_tab, safe_switch_to
        
        try:
            def _find():
                wins = self.gw.getWindowsWithTitle(profile.window_tag)
                if wins:
                    return wins
                for w in self.gw.getAllWindows():
                    if profile.window_tag in (w.title or ""):
                        return [w]
                return []

            windows = _find()

            # Если не нашли — попробуем активировать tag tab и поискать ещё раз
            if not windows and profile.driver:
                try:
                    ensure_tag_tab(profile)
                    if profile.tag_window_handle:
                        safe_switch_to(profile.driver, profile.tag_window_handle)
                        time.sleep(0.2)  # дать ОС обновить заголовок
                    windows = _find()
                except Exception:
                    windows = _find()

            if not windows:
                logging.warning("Window with tag '%s' not found for profile %d", profile.window_tag, profile.profile_no)
                return False

            win = windows[0]

            try:
                if getattr(win, "isMinimized", False):
                    win.restore()
                    time.sleep(0.15)
            except Exception:
                pass

            try:
                win.activate()
                time.sleep(0.15)
            except Exception:
                pass

            try:
                win.maximize()
                time.sleep(0.2)
            except Exception:
                # уже максимизировано или maximize не поддержан — не критично
                pass

            logging.info("✓ Profile %d window focused and maximized: %s", profile.profile_no, win.title)
            return True

        except Exception as e:
            logging.error("Error focusing window for profile %d: %s", profile.profile_no, e)
            return False
    
    def minimize(self, profile: Profile) -> bool:
        """Минимизировать окно профиля."""
        if not self._available:
            return False
        
        try:
            def _find_windows():
                wins = self.gw.getWindowsWithTitle(profile.window_tag)
                if wins:
                    return wins
                for w in self.gw.getAllWindows():
                    if profile.window_tag in (w.title or ""):
                        return [w]
                return []

            windows = _find_windows()

            # Если Medium активен и title не содержит tag — временно активируем tag-tab
            if not windows and getattr(profile, "driver", None):
                from poster.adspower.tabs import ensure_tag_tab, safe_switch_to
                try:
                    ensure_tag_tab(profile)
                    if profile.tag_window_handle:
                        safe_switch_to(profile.driver, profile.tag_window_handle)
                        time.sleep(0.2)
                    windows = _find_windows()
                except Exception:
                    windows = _find_windows()

            if windows:
                windows[0].minimize()
                logging.debug("Profile %d window minimized", profile.profile_no)
                return True

            return False
        except Exception as e:
            logging.debug("Error minimizing window for profile %d: %s", profile.profile_no, e)
            return False

