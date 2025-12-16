"""
poster.adspower.window_manager

Управление окном браузера. Основная цель:
- вывести окно нужного профиля на передний план
- восстановить (если minimised) и максимизировать

Алгоритм:
1) по возможности используем Win32 HWND через PID (если доступен pywin32)
2) иначе – pygetwindow по title (стабилизируется tag-tab)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from poster.models import Profile


class WindowManager:
    """Менеджер для работы с окнами браузера."""

    def __init__(self):
        # pygetwindow – удобный, но хрупкий
        self.gw = None
        try:
            import pygetwindow as gw  # type: ignore
            self.gw = gw
        except Exception:
            self.gw = None

        # pywin32 – более низкоуровневый и надёжный
        self._win32 = None
        try:
            import win32con  # type: ignore
            import win32gui  # type: ignore
            import win32process  # type: ignore
            self._win32 = (win32con, win32gui, win32process)
        except Exception:
            self._win32 = None

    # -------------------------
    # Win32 path (best effort)
    # -------------------------
    def _find_hwnd_by_pid(self, pid: int) -> Optional[int]:
        if not self._win32:
            return None
        win32con, win32gui, win32process = self._win32

        matches = []

        def enum_handler(hwnd, _):
            try:
                _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                if wpid != pid:
                    return
                # Только видимые окна
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd) or ""
                if title.strip():
                    matches.append(hwnd)
            except Exception:
                return

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception:
            return None

        return matches[0] if matches else None

    def _win32_focus_maximize(self, hwnd: int) -> bool:
        if not self._win32:
            return False
        win32con, win32gui, _ = self._win32
        try:
            # restore if minimized, then bring to front, then maximize
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.05)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.1)
            return True
        except Exception as e:
            logging.debug("win32_focus_maximize failed: %s", e)
            return False

    # -------------------------
    # pygetwindow path
    # -------------------------
    def _find_pygetwindow(self, title_fragment: str):
        if not self.gw:
            return None
        try:
            wins = self.gw.getWindowsWithTitle(title_fragment) or []
            if wins:
                return wins[0]
            for w in self.gw.getAllWindows() or []:
                if title_fragment and title_fragment in (w.title or ""):
                    return w
        except Exception:
            return None
        return None

    def focus(self, profile: Profile, retries: int = 6, sleep_s: float = 0.35) -> bool:
        """
        Вывести окно профиля на передний план и максимизировать.
        Требует стабильного window_tag в заголовке активной вкладки (для pygetwindow),
        поэтому рекомендуется перед вызовом активировать tag-tab.
        """
        tag = getattr(profile, "window_tag", "") or ""
        pid = getattr(profile, "pid", None) or getattr(profile, "browser_pid", None)

        # 1) Win32 по PID (если есть)
        if pid and self._win32:
            try:
                hwnd = self._find_hwnd_by_pid(int(pid))
                if hwnd:
                    return self._win32_focus_maximize(hwnd)
            except Exception:
                pass

        # 2) pygetwindow по заголовку (fallback)
        if not self.gw:
            logging.warning("WindowManager: pygetwindow not available and no win32 pid path.")
            return False

        from poster.adspower.tabs import ensure_tag_tab, safe_switch_to, find_window_by_tag

        for attempt in range(max(1, retries)):
            try:
                # Подстрахуем title: если есть driver – активируем tag-tab
                if getattr(profile, "driver", None):
                    ensure_tag_tab(profile)
                    h = find_window_by_tag(profile)
                    if h:
                        safe_switch_to(profile.driver, h)
                        time.sleep(0.2)

                w = self._find_pygetwindow(tag)
                if not w:
                    time.sleep(sleep_s)
                    continue

                # restore/activate/maximize
                try:
                    if getattr(w, "isMinimized", False):
                        w.restore()
                        time.sleep(0.1)
                except Exception:
                    pass

                try:
                    w.activate()
                except Exception:
                    pass
                time.sleep(0.15)

                try:
                    w.maximize()
                except Exception:
                    pass
                time.sleep(0.15)

                # Вторая попытка activate (часто помогает)
                try:
                    w.activate()
                except Exception:
                    pass

                # Проверка (не всегда доступно)
                return True
            except Exception as e:
                logging.debug("WindowManager focus attempt %d failed: %s", attempt + 1, e)
                time.sleep(sleep_s)

        return False

    def minimize(self, profile: Profile) -> bool:
        """Минимизировать окно профиля (best effort)."""
        if not self.gw:
            return False
        tag = getattr(profile, "window_tag", "") or ""
        w = self._find_pygetwindow(tag)
        if not w:
            return False
        try:
            w.minimize()
            return True
        except Exception:
            return False
