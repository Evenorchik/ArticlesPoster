"""
Координаты для кликов и задержки.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Coords:
    """Координаты для кликов на экране."""
    # Medium coordinates
    TITLE_INPUT: Tuple[int, int] = (633, 214)        # Шаг 3: ввод текста (title)
    PUBLISH_BUTTON_1: Tuple[int, int] = (1301, 118)  # Шаг 7: первая кнопка Publish
    HASHTAGS_INPUT: Tuple[int, int] = (1037, 440)     # Шаг 8: поле ввода хэштегов
    PUBLISH_BUTTON_2: Tuple[int, int] = (1051, 602)   # Шаг 10: финальная кнопка Publish
    PUBLISH_BUTTON_2_ALT: Tuple[int, int] = (1060, 573)
    BODY_TEXT: Tuple[int, int] = (621, 270)
    PLUS_BUTTON: Tuple[int, int] = (559, 268)
    IMAGE_BUTTON: Tuple[int, int] = (612, 267)
    
    # Quora coordinates
    QUORA_EMPTY_CLICK: Tuple[int, int] = (1815, 194)  # Empty click to guarantee focus
    QUORA_CREATE_POST: Tuple[int, int] = (1023, 216)  # Click Create post button
    QUORA_TEXT_FIELD: Tuple[int, int] = (699, 461)    # Click on text field button
    QUORA_IMAGE_UPLOAD: Tuple[int, int] = (653, 837)   # Click on image upload button
    QUORA_POST_BUTTON: Tuple[int, int] = (1267, 834)  # Click Post button


@dataclass
class Delays:
    """Задержки между действиями (базовые значения, будут рандомизированы)."""
    # Medium delays
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
    
    # Quora delays
    QUORA_AFTER_OPEN_TAB: float = 15  # Wait after opening Quora tab
    QUORA_AFTER_EMPTY_CLICK: float = 3  # Wait after empty click
    QUORA_AFTER_CREATE_POST: float = 10  # Wait after clicking Create post
    QUORA_AFTER_TEXT_FIELD: float = 3  # Wait after clicking text field
    QUORA_AFTER_IMAGE_UPLOAD: float = 10  # Wait after clicking image upload
    QUORA_AFTER_POST: float = 10  # Wait after clicking Post button


# Глобальные экземпляры для удобства
coords = Coords()
delays = Delays()


