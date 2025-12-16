# -*- coding: utf-8 -*-
"""
click_debug_screenshots.py

Утилита для отладки PyAutoGUI-кликов:
- делает скриншот всего экрана
- отмечает заданные координаты (x, y) крестом + кругом
- подписывает координаты и опциональный label
- сохраняет PNG (и опционально "зум"-кроп вокруг точки)

Задумка: вы вставляете вызов capture_click_screenshot((x, y), label="STEP 2 title")
рядом с каждым кликом, чтобы быстро видеть: куда именно "целимся" и что было на экране.

Зависимости:
- pyautogui
- pillow (PIL)  -> обычно ставится автоматически вместе с pyautogui, но лучше явно: pip install pillow
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, Union

import pyautogui

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:
    _PIL_OK = False


Point = Tuple[int, int]


@dataclass
class ScreenshotResult:
    full_path: str
    zoom_path: Optional[str] = None


def _safe_mkdir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _ts() -> str:
    # 2025-12-14_23-59-59_123
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]


def _try_font(size: int = 18):
    # PIL может не найти системный шрифт — fallback на дефолтный.
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


def capture_click_screenshot(
    coords: Union[Point, Tuple[float, float]],
    *,
    label: str = "",
    out_dir: str = "debug_click_shots",
    prefix: str = "click",
    draw_color: Tuple[int, int, int] = (255, 0, 0),
    radius: int = 14,
    crosshair: int = 18,
    line_width: int = 4,
    add_zoom_crop: bool = True,
    zoom_size: int = 420,
    sleep_before: float = 0.0,
) -> ScreenshotResult:
    """
    Делает скриншот экрана и отмечает coords (x, y).

    Args:
        coords: (x, y) экранные координаты
        label: подпись (например "STEP 2: Title click")
        out_dir: папка для сохранения
        prefix: префикс имени файла
        draw_color: цвет отметки
        radius: радиус круга вокруг точки
        crosshair: длина "лучей" крестика
        line_width: толщина линий
        add_zoom_crop: сохранить дополнительный кроп вокруг точки
        zoom_size: размер стороны кропа (px)
        sleep_before: пауза перед скриншотом (если нужно дождаться анимации)

    Returns:
        ScreenshotResult(full_path, zoom_path)
    """
    if not _PIL_OK:
        raise RuntimeError("Pillow (PIL) не доступен. Установите: pip install pillow")

    x, y = int(coords[0]), int(coords[1])

    if sleep_before and sleep_before > 0:
        time.sleep(float(sleep_before))

    _safe_mkdir(out_dir)

    ts = _ts()
    safe_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label)[:60]
    name_base = f"{prefix}_{ts}"
    if safe_label:
        name_base += f"_{safe_label}"

    full_path = os.path.join(out_dir, f"{name_base}.png")
    zoom_path = os.path.join(out_dir, f"{name_base}_zoom.png") if add_zoom_crop else None

    # pyautogui.screenshot() возвращает PIL.Image
    img = pyautogui.screenshot()
    draw = ImageDraw.Draw(img)

    # Круг
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        outline=draw_color,
        width=line_width,
    )

    # Крестик
    draw.line((x - crosshair, y, x + crosshair, y), fill=draw_color, width=line_width)
    draw.line((x, y - crosshair, x, y + crosshair), fill=draw_color, width=line_width)

    # Подпись
    text = f"({x}, {y})"
    if label:
        text = f"{label}  {text}"

    font = _try_font(18)
    # Чтобы текст был читаемым — рисуем подложку
    pad = 6
    text_w, text_h = draw.textbbox((0, 0), text, font=font)[2:]
    box_x1, box_y1 = x + 20, y + 20
    box_x2, box_y2 = box_x1 + text_w + 2 * pad, box_y1 + text_h + 2 * pad

    # если подпись выходит за край, сместим влево/вверх
    img_w, img_h = img.size
    if box_x2 > img_w:
        box_x1 = max(0, x - 20 - (text_w + 2 * pad))
        box_x2 = box_x1 + text_w + 2 * pad
    if box_y2 > img_h:
        box_y1 = max(0, y - 20 - (text_h + 2 * pad))
        box_y2 = box_y1 + text_h + 2 * pad

    draw.rectangle((box_x1, box_y1, box_x2, box_y2), fill=(0, 0, 0, 160))
    draw.text((box_x1 + pad, box_y1 + pad), text, font=font, fill=(255, 255, 255))

    img.save(full_path)

    # Дополнительный "зум" вокруг точки
    if add_zoom_crop and zoom_path:
        half = int(zoom_size // 2)
        left = max(0, x - half)
        top = max(0, y - half)
        right = min(img_w, x + half)
        bottom = min(img_h, y + half)
        crop = img.crop((left, top, right, bottom))

        # В кропе повторим маркер в центре
        cx, cy = x - left, y - top
        cdraw = ImageDraw.Draw(crop)
        cdraw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=draw_color, width=line_width)
        cdraw.line((cx - crosshair, cy, cx + crosshair, cy), fill=draw_color, width=line_width)
        cdraw.line((cx, cy - crosshair, cx, cy + crosshair), fill=draw_color, width=line_width)

        crop.save(zoom_path)

    return ScreenshotResult(full_path=full_path, zoom_path=zoom_path)


def click_with_debug(
    coords: Union[Point, Tuple[float, float]],
    *,
    label: str = "",
    out_dir: str = "debug_click_shots",
    before: bool = True,
    after: bool = False,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.0,
    move_duration: float = 0.0,
) -> ScreenshotResult:
    """
    Удобный хелпер: делает скриншот(ы) и кликает.

    По умолчанию:
      - скриншот ДО клика
      - кликает
      - после — не снимает (можно включить after=True)

    Возвращает результат последнего скриншота (after, если включен, иначе before).
    """
    last = None
    if before:
        last = capture_click_screenshot(coords, label=label + "_before" if label else "before", out_dir=out_dir)

    x, y = int(coords[0]), int(coords[1])
    pyautogui.moveTo(x, y, duration=float(move_duration))
    pyautogui.click(x, y, clicks=int(clicks), interval=float(interval), button=button)

    if after:
        last = capture_click_screenshot(coords, label=label + "_after" if label else "after", out_dir=out_dir)

    # last гарантированно будет не None, если before=True или after=True
    if last is None:
        last = ScreenshotResult(full_path="")
    return last
