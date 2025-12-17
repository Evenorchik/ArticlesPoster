"""
Получение URL опубликованной статьи на Quora через Selenium.
"""
import time
import logging
import pyperclip
from typing import Optional
from poster.models import Profile
from poster.adspower.tabs import safe_switch_to
from poster.ui.interface import UiDriver


def fetch_published_url(profile: Profile, ui: Optional[UiDriver] = None, wait_after_publish: float = 5.0) -> Optional[str]:
    """
    Получить URL опубликованной статьи на Quora через Selenium.
    
    Args:
        profile: Профиль с подключенным driver
        ui: UI драйвер для fallback (опционально)
        wait_after_publish: Задержка после публикации перед захватом URL (секунды)
    
    Returns:
        URL статьи или None
    """
    logging.info("STEP 11: Getting published Quora article URL via Selenium...")
    
    # Ждем, пока URL изменится на финальный
    logging.info("  Waiting %.1f seconds for URL to update after publish...", wait_after_publish)
    if ui:
        ui.sleep(wait_after_publish)
    else:
        time.sleep(wait_after_publish)
    
    url = None
    try:
        if profile.driver and profile.quora_window_handle:
            try:
                safe_switch_to(profile.driver, profile.quora_window_handle)
            except (Exception, AttributeError) as e:
                logging.debug("Window handle invalid, searching for Quora window: %s", e)
                all_windows = profile.driver.window_handles
                for window in all_windows:
                    try:
                        profile.driver.switch_to.window(window)
                        current_url = profile.driver.current_url
                        if 'quora.com' in current_url:
                            profile.quora_window_handle = window
                            break
                    except (Exception, AttributeError):
                        continue
                else:
                    if all_windows:
                        profile.driver.switch_to.window(all_windows[-1])

        if profile.driver:
            # Ждем, пока URL станет финальным (не содержит /write или /compose)
            max_wait_time = 10.0  # Максимальное время ожидания
            check_interval = 0.5  # Интервал проверки
            waited = 0.0
            
            while waited < max_wait_time:
                url = profile.driver.current_url
                
                # Проверяем, что URL не содержит /write или /compose
                if url and 'quora.com' in url:
                    if '/write' not in url and '/compose' not in url:
                        logging.info("  ✓ URL retrieved via Selenium (final URL)")
                        logging.info("  Retrieved URL: %s", url)
                        break
                    else:
                        logging.debug("  URL still contains /write or /compose, waiting... (current: %s)", url)
                        if ui:
                            ui.sleep(check_interval)
                        else:
                            time.sleep(check_interval)
                        waited += check_interval
                else:
                    # Если URL еще не готов, ждем
                    if ui:
                        ui.sleep(check_interval)
                    else:
                        time.sleep(check_interval)
                    waited += check_interval
            
            # Если после ожидания URL все еще содержит /write, берем текущий URL
            if waited >= max_wait_time:
                url = profile.driver.current_url
                if url and ('/write' in url or '/compose' in url):
                    logging.warning("  ⚠ URL still contains /write or /compose after waiting, but using it anyway")
                    logging.warning("  Retrieved URL: %s", url)
                elif url:
                    logging.info("  ✓ URL retrieved via Selenium")
                    logging.info("  Retrieved URL: %s", url)
                else:
                    logging.error("  ✗ Failed to get URL from driver")
                    url = None
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
        logging.info("✓ Quora article published successfully!")
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

