"""
Утилиты для работы с задержками и таймингами.
"""
import time
import logging
import random


def random_delay(base_seconds: float, variance_percent: float = 10.0) -> float:
    """Генерирует случайную задержку с вариацией."""
    variance = base_seconds * (variance_percent / 100.0)
    min_delay = base_seconds - variance
    max_delay = base_seconds + variance
    delay = random.uniform(min_delay, max_delay)
    return delay


def wait_with_log(seconds: float, step_name: str, variance_percent: float = 10.0):
    """Ожидание с логированием и случайной вариацией."""
    actual_delay = random_delay(seconds, variance_percent)
    logging.debug(
        "  [%s] Waiting %.2f seconds (base: %.1f ±%.0f%%)",
        step_name, actual_delay, seconds, variance_percent
    )
    time.sleep(actual_delay)

