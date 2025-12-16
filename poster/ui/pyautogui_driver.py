"""
Реализация UiDriver через PyAutoGUI.
"""
import time
import pyautogui
import pyperclip
from typing import Tuple
from click_debug_screenshots import capture_click_screenshot
from poster.ui.interface import UiDriver


# Настройка PyAutoGUI
pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True


class PyAutoGuiDriver:
    """Реализация UiDriver через PyAutoGUI."""
    
    def click(self, x: int, y: int) -> None:
        """Кликнуть по координатам."""
        pyautogui.click(x, y)
    
    def hotkey(self, *keys: str) -> None:
        """Нажать комбинацию клавиш."""
        pyautogui.hotkey(*keys)
    
    def press(self, key: str) -> None:
        """Нажать одну клавишу."""
        pyautogui.press(key)
    
    def write(self, text: str, interval: float = 0.0) -> None:
        """Ввести текст."""
        pyautogui.write(text, interval=interval)
    
    def sleep(self, seconds: float) -> None:
        """Пауза."""
        time.sleep(seconds)
    
    def screenshot_on_click(self, coords: Tuple[int, int], label: str = "") -> None:
        """Сделать скриншот перед кликом (для отладки)."""
        capture_click_screenshot(coords, label=label)
    
    def copy(self, text: str) -> None:
        """Скопировать текст в буфер обмена."""
        pyperclip.copy(text)
    
    def paste(self) -> str:
        """Вставить текст из буфера обмена."""
        return pyperclip.paste()

