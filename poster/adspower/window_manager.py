"""
poster.adspower.window_manager

Управление окном браузера. Основная цель:
- вывести окно нужного профиля на передний план
- восстановить (если minimised) и максимизировать

Стратегии (по убыванию надёжности):
1) Win32 HWND через PID (если доступен pywin32)
   - PID берём из profile.pid/profile.browser_pid
   - если PID не задан, пытаемся вычислить его по debuggerAddress (selenium_address/driver.capabilities)
2) WebDriver maximize_window() (best-effort)
3) pygetwindow по title (fallback; может не работать в AdsPower-сборках)

Важно: для UI-автоматизации (PyAutoGUI) фокус окна критичен. Если не удалось — хоткеи улетят в консоль.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

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

        # psutil – чтобы получить PID по debugger port
        self.psutil = None
        try:
            import psutil  # type: ignore
            self.psutil = psutil
        except Exception:
            self.psutil = None

    # -------------------------
    # DebuggerAddress -> PID
    # -------------------------
    @staticmethod
    def _parse_host_port(addr: str) -> Tuple[Optional[str], Optional[int]]:
        if not addr:
            return None, None
        s = addr.strip()
        if ":" not in s:
            return s, None
        host, port_s = s.rsplit(":", 1)
        try:
            return host, int(port_s)
        except Exception:
            return host, None

    def _get_debugger_address(self, profile: Profile) -> Optional[str]:
        # 1) То, что положили в профиль
        addr = getattr(profile, "selenium_address", None)
        if addr:
            return str(addr)

        # 2) Попробуем вытащить из capabilities
        driver = getattr(profile, "driver", None)
        if not driver:
            return None
        try:
            caps = driver.capabilities or {}
            copt = (caps.get("goog:chromeOptions") or {}) if isinstance(caps, dict) else {}
            dbg = copt.get("debuggerAddress")
            if dbg:
                return str(dbg)
        except Exception:
            pass
        return None

    def _pid_from_debugger_port(self, port: int) -> Optional[int]:
        """
        Найти PID процесса, который слушает TCP port (debuggerAddress).
        Работает только если установлен psutil.
        """
        if not self.psutil or not port:
            return None

        try:
            conns = self.psutil.net_connections(kind="tcp")
        except Exception:
            return None

        # 1) Ищем LISTEN на этом порту
        for c in conns:
            try:
                if c.laddr and getattr(c.laddr, "port", None) == port and c.pid:
                    # На Windows LISTEN обычно имеет status == 'LISTEN'
                    if str(getattr(c, "status", "")).upper() in ("LISTEN", "LISTENING", ""):
                        return int(c.pid)
            except Exception:
                continue

        # 2) Если LISTEN не нашли, всё равно вернём первый PID, где локальный порт совпал
        for c in conns:
            try:
                if c.laddr and getattr(c.laddr, "port", None) == port and c.pid:
                    return int(c.pid)
            except Exception:
                continue

        return None

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
            time.sleep(0.12)
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

    # -------------------------
    # Public API
    # -------------------------
    def focus(self, profile: Profile, retries: int = 6, sleep_s: float = 0.35) -> bool:
        """
        Вывести окно профиля на передний план и максимизировать.

        Важно: перед вызовом полезно иметь tag-tab, но title может не попадать в заголовок окна AdsPower.
        Поэтому главный путь — PID через debugger port.
        """
        driver = getattr(profile, "driver", None)

        # 0) Best-effort: WebDriver maximize (иногда хватает даже без OS-фокуса)
        if driver:
            try:
                driver.maximize_window()
            except Exception:
                pass

        # 1) Соберём PID (из профиля или по debuggerAddress)
        pid = getattr(profile, "pid", None) or getattr(profile, "browser_pid", None)
        if not pid:
            dbg = self._get_debugger_address(profile)
            _, port = self._parse_host_port(dbg or "")
            if port:
                pid = self._pid_from_debugger_port(port)
                if pid:
                    try:
                        setattr(profile, "pid", int(pid))
                    except Exception:
                        pass

        # 2) Win32 по PID
        if pid and self._win32:
            try:
                hwnd = self._find_hwnd_by_pid(int(pid))
                if hwnd:
                    if self._win32_focus_maximize(hwnd):
                        return True
            except Exception:
                pass

        # 3) Fallback: pygetwindow по title (может не работать)
        tag = getattr(profile, "window_tag", "") or ""
        if not self.gw:
            if pid and not self._win32:
                logging.warning(
                    "WindowManager: found pid=%s but pywin32 not available; cannot OS-focus window reliably.",
                    pid,
                )
            else:
                logging.warning("WindowManager: pygetwindow not available and no win32 pid path.")
            return False

        # Чтобы увеличить шанс совпадения title — сделаем tag-tab активным (без навигации)
        if driver:
            try:
                from poster.adspower.tabs import ensure_tag_tab, safe_switch_to, find_window_by_tag
                ensure_tag_tab(profile)
                h = find_window_by_tag(profile)
                if h:
                    safe_switch_to(driver, h)
                    time.sleep(0.15)
            except Exception:
                pass

        for attempt in range(max(1, retries)):
            try:
                w = self._find_pygetwindow(tag)
                if not w:
                    time.sleep(sleep_s)
                    continue

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

                try:
                    w.activate()
                except Exception:
                    pass

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
