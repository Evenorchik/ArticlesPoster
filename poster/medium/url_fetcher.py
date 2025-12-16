"""
Получение URL опубликованной статьи через Selenium.
"""
import time
import logging
import pyperclip
from typing import Optional
from poster.models import Profile
from poster.adspower.tabs import safe_switch_to
from poster.ui.interface import UiDriver


def fetch_published_url(profile: Profile, ui: Optional[UiDriver] = None) -> Optional[str]:
    """
    Получить URL опубликованной статьи через Selenium.
    
    Args:
        profile: Профиль с подключенным driver
        ui: UI драйвер для fallback (опционально)
    
    Returns:
        URL статьи или None
    """
    logging.info("STEP 10: Getting published article URL via Selenium...")
    try:
        if profile.driver and profile.medium_window_handle:
            try:
                safe_switch_to(profile.driver, profile.medium_window_handle)
            except (Exception, AttributeError) as e:
                logging.debug("Window handle invalid, searching for Medium window: %s", e)
                all_windows = profile.driver.window_handles
                for window in all_windows:
                    try:
                        profile.driver.switch_to.window(window)
                        current_url = profile.driver.current_url
                        if 'medium.com' in current_url and '/@' in current_url:
                            profile.medium_window_handle = window
                            break
                    except (Exception, AttributeError):
                        continue
                else:
                    if all_windows:
                        profile.driver.switch_to.window(all_windows[-1])

        if profile.driver:
            url = profile.driver.current_url
            logging.info("  ✓ URL retrieved via Selenium")
            logging.info("  Retrieved URL: %s", url)
        else:
            if ui:
                logging.warning("  Driver not available, using PyAutoGUI fallback...")
                ui.hotkey('ctrl', 'l')
                ui.sleep(0.5)
                ui.hotkey('ctrl', 'c')
                ui.sleep(1)
                url = pyperclip.paste()
                logging.info("  ✓ URL copied from clipboard (fallback)")
                logging.info("  Retrieved URL: %s", url)
            else:
                logging.error("  Driver not available and no UI fallback")
                return None
    except Exception as e:
        logging.error("  ✗ Failed to get URL: %s", e)
        return None

    if url and url.startswith('http'):
        logging.info("="*60)
        logging.info("✓ Article published successfully!")
        logging.info("URL: %s", url)
        logging.info("="*60)
        return url
    else:
        logging.warning("="*60)
        logging.warning("⚠ URL not retrieved or invalid")
        logging.warning("  Clipboard content: %s", url)
        logging.warning("  Expected: URL starting with 'http'")
        logging.warning("="*60)
        return None

