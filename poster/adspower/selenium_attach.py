"""
poster.adspower.selenium_attach

Подключение Selenium к уже запущенному профилю AdsPower (через remote debugging).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

SELENIUM_AVAILABLE = True
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
except Exception:  # pragma: no cover
    SELENIUM_AVAILABLE = False
    webdriver = None  # type: ignore
    Options = None  # type: ignore
    Service = None  # type: ignore


def attach_driver(selenium_address: str, webdriver_path: str) -> Optional["webdriver.Chrome"]:
    """
    Подключает webdriver к уже запущенному Chrome в AdsPower.

    selenium_address: строка вида "127.0.0.1:xxxxx"
    webdriver_path: путь к chromedriver.exe (AdsPower возвращает его в /active)
    """
    if not SELENIUM_AVAILABLE:
        logging.error("Selenium is not available. Install selenium>=4.")
        return None

    if not selenium_address:
        logging.error("attach_driver: empty selenium_address")
        return None
    if not webdriver_path:
        logging.error("attach_driver: empty webdriver_path")
        return None

    # Иногда AdsPower возвращает путь с кавычками/пробелами – нормализуем.
    webdriver_path = webdriver_path.strip().strip('"').strip("'")
    if os.path.isdir(webdriver_path):
        # Бывает, что передают директорию – попробуем найти внутри chromedriver(.exe)
        cand = None
        for name in ("chromedriver.exe", "chromedriver"):
            p = os.path.join(webdriver_path, name)
            if os.path.exists(p):
                cand = p
                break
        if cand:
            webdriver_path = cand

    try:
        opts = Options()
        # Важно: attach к уже существующему браузеру
        opts.add_experimental_option("debuggerAddress", selenium_address)

        service = Service(executable_path=webdriver_path)
        driver = webdriver.Chrome(service=service, options=opts)

        # Быстрая проверка
        _ = driver.window_handles
        logging.info("✓ Selenium attached (%s)", selenium_address)
        return driver
    except Exception as e:
        logging.error("✗ attach_driver failed (addr=%s, driver=%s): %s", selenium_address, webdriver_path, e)
        return None
