"""
Подключение Selenium к Ads Power профилю.
"""
import logging
from typing import Optional

# Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logging.warning("Selenium not available. Install with: pip install selenium")


def attach_driver(selenium_address: str, webdriver_path: str) -> Optional[webdriver.Chrome]:
    """Подключить Selenium WebDriver к уже запущенному Ads Power профилю."""
    if not SELENIUM_AVAILABLE:
        logging.error("Selenium not available! Install with: pip install selenium")
        return None
    
    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", selenium_address)

        service = Service(webdriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        logging.debug("✓ Selenium driver attached to profile")
        return driver
    except Exception as e:
        logging.error("Error creating Selenium driver: %s", e)
        return None

