"""
Модули для работы с UI через PyAutoGUI.
"""
from poster.ui.interface import UiDriver
from poster.ui.pyautogui_driver import PyAutoGuiDriver
from poster.ui.coords import Coords, Delays

__all__ = [
    'UiDriver',
    'PyAutoGuiDriver',
    'Coords',
    'Delays',
]

