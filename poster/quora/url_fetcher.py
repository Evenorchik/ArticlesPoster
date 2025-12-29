"""
Получение URL опубликованной статьи на Quora через Selenium.
"""
import time
import logging
import pyperclip
from typing import Optional
from poster.models import Profile
from poster.ui.interface import UiDriver
from poster.logging_helper import is_info_mode, log_info_short, log_debug_detailed


def fetch_published_url(profile: Profile, ui: Optional[UiDriver] = None, wait_after_publish: float = 8.0) -> Optional[str]:
    """
    Получить URL опубликованной статьи на Quora через Selenium.
    
    ВАЖНО: Берёт URL строго с ТЕКУЩЕЙ открытой вкладки, без переключений.
    
    Args:
        profile: Профиль с подключенным driver
        ui: UI драйвер для fallback (опционально)
        wait_after_publish: Задержка после публикации перед захватом URL (секунды)
    
    Returns:
        URL статьи или None
    """
    if is_info_mode():
        log_info_short("Получение URL опубликованной статьи")
    else:
        logging.info("STEP 11: Getting published Quora article URL via Selenium...")
    
    # Ждем, пока URL изменится на финальный
    log_debug_detailed(f"  Waiting {wait_after_publish:.1f} seconds for URL to update after publish...")
    if ui:
        ui.sleep(wait_after_publish)
    else:
        time.sleep(wait_after_publish)
    
    url = None
    try:
        if profile.driver:
            # ВАЖНО: Берём URL строго с ТЕКУЩЕЙ вкладки, без переключений и поисков
            url = profile.driver.current_url
            
            if url and is_info_mode():
                log_info_short(f"✓ URL получен: {url}")
            elif url:
                logging.info("  ✓ URL retrieved from current tab")
                logging.info("  Retrieved URL: %s", url)
        else:
            if ui:
                logging.warning("  Driver not available, using PyAutoGUI fallback...")
                ui.hotkey('ctrl', 'l')
                ui.sleep(0.5)
                ui.hotkey('ctrl', 'c')
                ui.sleep(1)
                url = pyperclip.paste()
                if is_info_mode():
                    log_info_short(f"✓ URL скопирован из буфера: {url}")
                else:
                    logging.info("  ✓ URL copied from clipboard (fallback)")
                    logging.info("  Retrieved URL: %s", url)
            else:
                logging.error("  Driver not available and no UI fallback")
                return None
    except Exception as e:
        logging.error("  ✗ Failed to get URL: %s", e)
        return None

    if url and url.startswith('http'):
        if not is_info_mode():
            logging.info("="*60)
            logging.info("✓ Quora article published successfully!")
            logging.info("URL: %s", url)
            logging.info("="*60)
        return url
    else:
        logging.warning("="*60)
        logging.warning("⚠ URL not retrieved or invalid")
        logging.warning("  Retrieved URL: %s", url)
        logging.warning("  Expected: URL starting with 'http'")
        logging.warning("="*60)
        return None

