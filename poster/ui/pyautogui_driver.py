"""
Реализация UiDriver через PyAutoGUI.
"""
import os
import time
import pyautogui
import pyperclip
from typing import Tuple, Optional
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

    # -----------------------------
    # Image-based clicking helpers
    # -----------------------------
    def locate_center_on_screen(
        self,
        image_path: str,
        confidence: float = 0.95,
        timeout_s: float = 12.0,
        grayscale: bool = True,
    ) -> Optional[Tuple[int, int]]:
        """
        Найти центр совпадения картинки на экране.

        Примечания:
        - confidence работает только при наличии OpenCV (opencv-python).
        - если OpenCV не установлен, будет попытка без confidence (точное совпадение).
        """
        if not image_path:
            return None

        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            return None

        deadline = time.time() + max(0.5, float(timeout_s))
        while time.time() < deadline:
            try:
                pt = pyautogui.locateCenterOnScreen(
                    abs_path,
                    confidence=confidence,
                    grayscale=grayscale,
                )
            except TypeError:
                # confidence unsupported (likely no opencv) → try exact match
                try:
                    pt = pyautogui.locateCenterOnScreen(abs_path, grayscale=grayscale)
                except Exception:
                    pt = None
            except Exception:
                pt = None

            if pt:
                # pt can be Point(x,y) or tuple-like
                try:
                    return (int(pt.x), int(pt.y))
                except Exception:
                    try:
                        return (int(pt[0]), int(pt[1]))
                    except Exception:
                        return None

            time.sleep(0.25)

        return None

    def click_image(
        self,
        image_path: str,
        confidence: float = 0.95,
        timeout_s: float = 12.0,
        grayscale: bool = True,
    ) -> bool:
        """Найти картинку на экране и кликнуть в центр. Возвращает True/False."""
        pt = self.locate_center_on_screen(
            image_path=image_path,
            confidence=confidence,
            timeout_s=timeout_s,
            grayscale=grayscale,
        )
        if not pt:
            return False
        self.click(pt[0], pt[1])
        return True

