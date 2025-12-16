"""
Юнит-тестер для проверки открытия профилей Ads Power и подготовки Medium вкладки.

Тестирует:
- Открытие профиля через API
- Подключение Selenium
- Фокус и максимизация окна
- Открытие Medium вкладки
- Скриншот экрана через 10 секунд после открытия Medium
- Закрытие профиля

Проходит по всем 10 профилям последовательно с паузами.
"""
import os
import time
import logging
from datetime import datetime
from typing import Optional
import pyautogui
from config import LOG_LEVEL

from poster.settings import (
    PROFILE_SEQUENTIAL_MAPPING,
    get_profile_id_by_sequential_no,
    get_profile_no_by_sequential_no,
)
from poster.models import Profile
from poster.adspower.api_client import AdsPowerApiClient
from poster.adspower.profile_manager import ProfileManager
from poster.adspower.window_manager import WindowManager
from poster.adspower.tabs import TabManager
from poster.ui import PyAutoGuiDriver

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы для тестирования
PROFILE_INTERVAL_SEC = 15  # Интервал между профилями (секунды)
MEDIUM_LOAD_WAIT_SEC = 5  # Ожидание загрузки Medium после открытия вкладки (секунды)
PROFILE_START_WAIT_SEC = 20  # Ожидание после открытия Medium вкладки на запуск профиля (секунды)
MIN_PAUSE_BETWEEN_ACTIONS = 1  # Минимальная пауза между действиями (секунды)
SCREENSHOT_DELAY_SEC = 10  # Задержка перед скриншотом после открытия Medium вкладки (секунды)
SCREENSHOTS_BASE_DIR = "profile_screenshots"  # Базовая папка для скриншотов


def take_screenshot(sequential_no: int, profile_no: int) -> Optional[str]:
    """
    Делает скриншот всего экрана и сохраняет в папку профиля.
    
    Args:
        sequential_no: Порядковый номер профиля (1-10)
        profile_no: Внутренний номер профиля
    
    Returns:
        Путь к сохраненному скриншоту или None при ошибке
    """
    try:
        # Создаем базовую папку для скриншотов
        os.makedirs(SCREENSHOTS_BASE_DIR, exist_ok=True)
        
        # Создаем папку для конкретного профиля
        profile_dir = os.path.join(SCREENSHOTS_BASE_DIR, f"profile_{sequential_no}_no_{profile_no}")
        os.makedirs(profile_dir, exist_ok=True)
        
        # Генерируем имя файла с timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_seq{sequential_no}_no{profile_no}_{timestamp}.png"
        filepath = os.path.join(profile_dir, filename)
        
        # Делаем скриншот
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        
        logging.info("✓ Screenshot saved: %s", filepath)
        return filepath
    except Exception as e:
        logging.error("✗ Error taking screenshot: %s", e, exc_info=True)
        return None


def test_single_profile(
    sequential_no: int,
    profile_manager: ProfileManager,
    window_manager: WindowManager,
    tab_manager: TabManager,
    ui: PyAutoGuiDriver
) -> bool:
    """
    Тестирует один профиль: открытие, подготовка Medium, закрытие.
    
    Args:
        sequential_no: Порядковый номер профиля (1-10)
        profile_manager: Менеджер профилей
        window_manager: Менеджер окон
        tab_manager: Менеджер вкладок
        ui: UI драйвер
    
    Returns:
        True если успешно, False при ошибке
    """
    logging.info("")
    logging.info("=" * 80)
    logging.info("TESTING PROFILE: Sequential No %d", sequential_no)
    logging.info("=" * 80)
    
    profile_id = get_profile_id_by_sequential_no(sequential_no)
    if not profile_id:
        logging.error("✗ Profile with sequential_no %d not found", sequential_no)
        return False
    
    profile_no = get_profile_no_by_sequential_no(sequential_no)
    if not profile_no:
        logging.error("✗ Profile_no not found for sequential_no %d", sequential_no)
        return False
    
    logging.info("Profile info: ID=%s, No=%d, Seq=%d", profile_id, profile_no, sequential_no)
    time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    
    # Шаг 1: Открытие профиля
    logging.info("")
    logging.info("STEP 1: Opening profile...")
    try:
        profile = profile_manager.ensure_ready(profile_no)
        if not profile:
            logging.error("✗ Failed to ensure profile %d is ready", profile_no)
            return False
        logging.info("✓ Profile opened and Selenium attached")
        time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    except Exception as e:
        logging.error("✗ Error opening profile: %s", e, exc_info=True)
        return False
    
    # Шаг 2: Фокус и максимизация окна
    logging.info("")
    logging.info("STEP 2: Focusing and maximizing window...")
    try:
        if not window_manager.focus(profile):
            logging.warning("⚠ Failed to focus/maximize window, but continuing...")
        else:
            logging.info("✓ Window focused and maximized")
        time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    except Exception as e:
        logging.error("✗ Error focusing window: %s", e, exc_info=True)
        # Продолжаем, так как это не критично
    
    # Шаг 3: Открытие Medium вкладки
    logging.info("")
    logging.info("STEP 3: Opening Medium tab...")
    try:
        if not tab_manager.ensure_medium_tab_open(profile, ui, window_manager, wait_after_open=MEDIUM_LOAD_WAIT_SEC):
            logging.error("✗ Failed to open Medium tab for profile %d", profile_no)
            # Пытаемся закрыть профиль даже при ошибке
            try:
                profile_manager.close(profile_no)
            except Exception:
                pass
            return False
        logging.info("✓ Medium tab opened and ready")
        time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    except Exception as e:
        logging.error("✗ Error opening Medium tab: %s", e, exc_info=True)
        # Пытаемся закрыть профиль даже при ошибке
        try:
            profile_manager.close(profile_no)
        except Exception:
            pass
        return False
    
    # Шаг 3.5: Скриншот через 10 секунд после открытия Medium вкладки
    logging.info("")
    logging.info("STEP 3.5: Waiting %d seconds before taking screenshot...", SCREENSHOT_DELAY_SEC)
    time.sleep(SCREENSHOT_DELAY_SEC)
    logging.info("Taking screenshot of the screen...")
    screenshot_path = take_screenshot(sequential_no, profile_no)
    if screenshot_path:
        logging.info("✓ Screenshot completed and saved")
    else:
        logging.warning("⚠ Screenshot failed, but continuing...")
    time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    
    # Шаг 4: Ожидание на запуск профиля (после открытия Medium вкладки)
    logging.info("")
    logging.info("STEP 4: Waiting %d seconds for profile to fully start...", PROFILE_START_WAIT_SEC)
    time.sleep(PROFILE_START_WAIT_SEC)
    logging.info("✓ Wait completed")
    
    # Шаг 5: Проверка состояния
    logging.info("")
    logging.info("STEP 5: Verifying profile state...")
    try:
        if profile.driver:
            current_url = profile.driver.current_url
            logging.info("  Current URL: %s", current_url)
            if 'medium.com' in current_url.lower():
                logging.info("✓ Profile is on Medium page")
            else:
                logging.warning("⚠ Profile is not on Medium page (URL: %s)", current_url)
        else:
            logging.warning("⚠ Driver not available for verification")
        time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    except Exception as e:
        logging.warning("⚠ Error verifying profile state: %s", e)
    
    # Шаг 6: Закрытие профиля
    logging.info("")
    logging.info("STEP 6: Closing profile...")
    try:
        if not profile_manager.close(profile_no):
            logging.error("✗ Failed to close profile %d", profile_no)
            return False
        logging.info("✓ Profile closed successfully")
        time.sleep(MIN_PAUSE_BETWEEN_ACTIONS)
    except Exception as e:
        logging.error("✗ Error closing profile: %s", e, exc_info=True)
        return False
    
    logging.info("")
    logging.info("=" * 80)
    logging.info("✓ PROFILE %d TEST COMPLETED SUCCESSFULLY", sequential_no)
    logging.info("=" * 80)
    return True


def test_all_profiles():
    """
    Тестирует все профили последовательно.
    """
    logging.info("")
    logging.info("=" * 80)
    logging.info("STARTING PROFILE OPEN UNIT TESTING")
    logging.info("=" * 80)
    logging.info("")
    logging.info("Configuration:")
    logging.info("  Profile interval: %d seconds", PROFILE_INTERVAL_SEC)
    logging.info("  Medium load wait: %d seconds", MEDIUM_LOAD_WAIT_SEC)
    logging.info("  Profile start wait: %d seconds", PROFILE_START_WAIT_SEC)
    logging.info("  Min pause between actions: %d seconds", MIN_PAUSE_BETWEEN_ACTIONS)
    logging.info("  Screenshot delay: %d seconds", SCREENSHOT_DELAY_SEC)
    logging.info("  Screenshots directory: %s", SCREENSHOTS_BASE_DIR)
    logging.info("")
    
    if not PROFILE_SEQUENTIAL_MAPPING:
        logging.error("PROFILE_SEQUENTIAL_MAPPING is empty! Cannot proceed.")
        return
    
    # Получаем список всех sequential_no (1-10)
    all_sequential_nos = sorted(PROFILE_SEQUENTIAL_MAPPING.values())
    if not all_sequential_nos:
        logging.error("No profiles found in PROFILE_SEQUENTIAL_MAPPING!")
        return
    
    logging.info("Found %d profiles to test: %s", len(all_sequential_nos), all_sequential_nos)
    logging.info("")
    
    # Инициализация компонентов
    logging.info("Initializing components...")
    api_client = AdsPowerApiClient()
    profile_manager = ProfileManager(api_client)
    window_manager = WindowManager()
    tab_manager = TabManager()
    ui = PyAutoGuiDriver()
    logging.info("✓ Components initialized")
    logging.info("")
    
    # Статистика
    total_profiles = len(all_sequential_nos)
    successful = 0
    failed = 0
    failed_profiles = []
    
    # Тестируем каждый профиль
    for idx, sequential_no in enumerate(all_sequential_nos, 1):
        logging.info("")
        logging.info(">>> PROFILE %d/%d <<<", idx, total_profiles)
        
        success = test_single_profile(
            sequential_no,
            profile_manager,
            window_manager,
            tab_manager,
            ui
        )
        
        if success:
            successful += 1
            logging.info("✓ Profile %d test PASSED", sequential_no)
        else:
            failed += 1
            failed_profiles.append(sequential_no)
            logging.error("✗ Profile %d test FAILED", sequential_no)
        
        # Пауза между профилями (кроме последнего)
        if idx < total_profiles:
            logging.info("")
            logging.info("Waiting %d seconds before next profile...", PROFILE_INTERVAL_SEC)
            time.sleep(PROFILE_INTERVAL_SEC)
    
    # Итоговая статистика
    logging.info("")
    logging.info("")
    logging.info("=" * 80)
    logging.info("TESTING COMPLETED")
    logging.info("=" * 80)
    logging.info("")
    logging.info("Results:")
    logging.info("  Total profiles tested: %d", total_profiles)
    logging.info("  Successful: %d", successful)
    logging.info("  Failed: %d", failed)
    logging.info("  Success rate: %.1f%%", (successful / total_profiles * 100) if total_profiles > 0 else 0)
    
    if failed_profiles:
        logging.info("")
        logging.warning("Failed profiles: %s", failed_profiles)
    else:
        logging.info("")
        logging.info("✓ All profiles tested successfully!")
    
    logging.info("")
    logging.info("=" * 80)


def main():
    """Главная функция."""
    try:
        test_all_profiles()
    except KeyboardInterrupt:
        logging.warning("")
        logging.warning("=" * 80)
        logging.warning("TESTING INTERRUPTED BY USER")
        logging.warning("=" * 80)
    except Exception as e:
        logging.error("")
        logging.error("=" * 80)
        logging.error("FATAL ERROR: %s", e, exc_info=True)
        logging.error("=" * 80)


if __name__ == "__main__":
    main()

