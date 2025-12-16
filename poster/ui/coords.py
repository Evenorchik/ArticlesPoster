"""
Координаты для кликов и задержки.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Coords:
    """Координаты для кликов на экране."""
    TITLE_INPUT: Tuple[int, int] = (633, 214)        # Шаг 3: ввод текста (title)
    PUBLISH_BUTTON_1: Tuple[int, int] = (1301, 118)  # Шаг 7: первая кнопка Publish
    HASHTAGS_INPUT: Tuple[int, int] = (1037, 440)     # Шаг 8: поле ввода хэштегов
    PUBLISH_BUTTON_2: Tuple[int, int] = (1051, 602)   # Шаг 10: финальная кнопка Publish


@dataclass
class Delays:
    """Задержки между действиями (базовые значения, будут рандомизированы)."""
    AFTER_OPEN_TAB: float = 15   # Шаг 2: ждём после открытия вкладки
    AFTER_TITLE_CLICK: float = 2  # Шаг 3: ждём после клика на поле title
    AFTER_TITLE_PASTE: float = 2  # Шаг 4: ждём после вставки title
    AFTER_ENTER: float = 2        # Шаг 5: ждём после Enter
    AFTER_BODY_PASTE: float = 2   # Шаг 6: ждём после вставки body
    AFTER_PUBLISH_1: float = 5    # Шаг 7: ждём после первой кнопки Publish
    AFTER_HASHTAGS_CLICK: float = 2  # Шаг 8: ждём после клика на поле хэштегов
    BETWEEN_HASHTAGS: float = 2      # Шаг 9: ждём между хэштегами
    AFTER_PUBLISH_2: float = 25      # Шаг 10: ждём после финальной кнопки Publish
    AFTER_COPY: float = 2            # Шаг 12: ждём после Ctrl+C


# Глобальные экземпляры для удобства
coords = Coords()
delays = Delays()

