"""
Вспомогательный модуль для условного логирования в зависимости от режима.
"""
import logging
from typing import Optional

# Глобальная переменная для режима логирования (устанавливается в scheduled_poster.py)
_LOG_MODE: str = "DEBUG"


def set_log_mode(mode: str):
    """Установить режим логирования (DEBUG или INFO)."""
    global _LOG_MODE
    _LOG_MODE = mode.upper()


def get_log_mode() -> str:
    """Получить текущий режим логирования."""
    return _LOG_MODE


def is_debug_mode() -> bool:
    """Проверить, включен ли режим DEBUG."""
    return _LOG_MODE == "DEBUG"


def is_info_mode() -> bool:
    """Проверить, включен ли режим INFO."""
    return _LOG_MODE == "INFO"


def log_step(step_name: str, message: str = ""):
    """
    Логирование шага в зависимости от режима.
    В INFO режиме: короткая одна строка
    В DEBUG режиме: подробное логирование
    """
    if is_info_mode():
        if message:
            logging.info("%s: %s", step_name, message)
        else:
            logging.info(step_name)
    else:
        if message:
            logging.info("%s: %s", step_name, message)
        else:
            logging.info(step_name)


def log_info_short(message: str):
    """Короткое логирование для INFO режима (всегда выводится)."""
    logging.info(message)


def log_debug_detailed(message: str):
    """Подробное логирование только для DEBUG режима."""
    if is_debug_mode():
        logging.debug(message)


def log_info_detailed(message: str):
    """Подробное логирование для DEBUG режима (через info)."""
    if is_debug_mode():
        logging.info(message)


def log_error(message: str, exc_info: bool = False):
    """Логирование ошибок (всегда выводится)."""
    logging.error(message, exc_info=exc_info)


def log_warning(message: str):
    """Логирование предупреждений (всегда выводится)."""
    logging.warning(message)

