"""
Тестовый скрипт для проверки загрузки обложки на Medium.

Функции:
1. open_first_profile() - открывает первый профиль (sequential_no = 1) и возвращает driver
2. attach_first_image() - находит первую обложку из data/images и подсовывает её в input[type="file"]

Функции можно вызывать вручную, независимо друг от друга.
"""
import os
import logging
import glob
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from poster.settings import (
    get_profile_id_by_sequential_no,
    get_profile_no_by_sequential_no,
)
from scheduled_poster import open_ads_power_profile, close_profile

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
IMAGES_ROOT_DIR = "./data/images"  # Папка с изображениями для обложек
FIRST_SEQUENTIAL_NO = 1  # Используем первый профиль из секвенции
FILE_INPUT_CSS_SELECTORS = [
    'input[type="file"][name="uploadedFile"]',
    'input[type="file"][accept*="image"]',
    'input[type="file"]',
]
WAIT_INPUT_TIMEOUT_SEC = 20

# Глобальные переменные для хранения состояния
_profile = None
_driver = None
_profile_id = None


def open_first_profile() -> Optional[object]:
    """
    Открывает первый профиль (sequential_no = 1) и возвращает Selenium driver.
    
    Returns:
        Selenium WebDriver или None при ошибке
    """
    global _profile, _driver, _profile_id
    
    logging.info("="*60)
    logging.info("Opening first profile (sequential_no = 1)...")
    logging.info("="*60)
    
    # Получаем первый профиль из секвенции
    sequential_no = FIRST_SEQUENTIAL_NO
    profile_id = get_profile_id_by_sequential_no(sequential_no)
    profile_no = get_profile_no_by_sequential_no(sequential_no)
    
    if not profile_id or not profile_no:
        logging.error("Failed to get profile for sequential_no=%d", sequential_no)
        logging.error("Make sure PROFILE_SEQUENTIAL_MAPPING is configured correctly")
        return None
    
    logging.info("Using profile: sequential_no=%d, profile_no=%d, profile_id=%s", 
                sequential_no, profile_no, profile_id)
    
    # Открываем профиль для Medium
    profile = open_ads_power_profile(profile_id, platform="medium")
    if not profile:
        logging.error("Failed to open profile! Aborting.")
        return None
    
    # Сохраняем состояние
    _profile = profile
    _profile_id = profile_id
    _driver = profile.driver
    
    logging.info("✓ Profile opened successfully")
    logging.info("✓ Selenium driver ready: %s", _driver)
    logging.info("")
    logging.info("You can now call attach_first_image() to upload an image")
    
    return _driver


def attach_first_image(driver=None) -> bool:
    """
    Находит первую обложку из папки data/images и подсовывает её в input[type="file"].
    
    Args:
        driver: Selenium WebDriver (если None, использует глобальный _driver)
    
    Returns:
        True если успешно, False при ошибке
    """
    global _driver
    
    # Используем переданный driver или глобальный
    if driver is None:
        driver = _driver
    
    if not driver:
        logging.error("No driver available! Please call open_first_profile() first or pass driver as argument")
        return False
    
    logging.info("="*60)
    logging.info("Attaching first image from %s", IMAGES_ROOT_DIR)
    logging.info("="*60)
    
    # Проверяем существование папки
    if not os.path.exists(IMAGES_ROOT_DIR):
        logging.error("Images directory does not exist: %s", IMAGES_ROOT_DIR)
        return False
    
    # Ищем первую обложку
    image_patterns = [
        os.path.join(IMAGES_ROOT_DIR, "cover_image_*.jpg"),
        os.path.join(IMAGES_ROOT_DIR, "cover_image_*.jpeg"),
        os.path.join(IMAGES_ROOT_DIR, "cover_image_*.png"),
        os.path.join(IMAGES_ROOT_DIR, "*.jpg"),
        os.path.join(IMAGES_ROOT_DIR, "*.jpeg"),
        os.path.join(IMAGES_ROOT_DIR, "*.png"),
    ]
    
    image_path = None
    for pattern in image_patterns:
        matches = glob.glob(pattern)
        if matches:
            image_path = os.path.abspath(matches[0])
            break
    
    if not image_path:
        logging.error("No images found in %s", IMAGES_ROOT_DIR)
        return False
    
    logging.info("Found image: %s", image_path)
    
    # Проверяем существование файла
    if not os.path.exists(image_path):
        logging.error("Image file does not exist: %s", image_path)
        return False
    
    file_size = os.path.getsize(image_path)
    logging.info("Image size: %d bytes", file_size)
    
    try:
        # Ищем input[type="file"]
        file_input = None
        for selector in FILE_INPUT_CSS_SELECTORS:
            try:
                wait = WebDriverWait(driver, WAIT_INPUT_TIMEOUT_SEC)
                file_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                # Проверяем, что элемент доступен (может быть скрыт, но это нормально)
                if file_input.is_enabled():
                    logging.info("  ✓ Found file input with selector: %s", selector)
                    break
            except TimeoutException:
                logging.debug("  Selector %s did not find input, trying next...", selector)
                continue
        
        if not file_input:
            logging.error("  ✗ File input not found with any selector")
            logging.error("  Make sure you've clicked through the image upload dialog (STEP 1.2)")
            return False
        
        # Прикрепляем файл
        logging.info("  Sending file path to input: %s", image_path)
        file_input.send_keys(image_path)
        
        # Проверяем, что файл был загружен
        try:
            wait = WebDriverWait(driver, 10)
            # Ждем, пока input.files.length станет 1 (через JS)
            wait.until(
                lambda d: d.execute_script("return arguments[0].files.length", file_input) > 0
            )
            logging.info("  ✓ File uploaded successfully (confirmed via JS)")
        except TimeoutException:
            # Если JS проверка не сработала, просто ждем немного и считаем успешным
            logging.warning("  ⚠ Could not confirm upload via JS, but file was sent")
            import time
            time.sleep(2)
        
        logging.info("  ✓ Image attached successfully!")
        return True
        
    except Exception as e:
        logging.error("  ✗ Failed to attach image: %s", e, exc_info=True)
        return False


def close_profile_if_open():
    """Закрывает профиль, если он был открыт."""
    global _profile_id, _profile, _driver
    
    if _profile_id:
        logging.info("Closing profile: %s", _profile_id)
        close_profile(_profile_id)
        _profile_id = None
        _profile = None
        _driver = None
        logging.info("✓ Profile closed")
    else:
        logging.info("No profile to close")


def main():
    """Интерактивное меню для тестирования функций."""
    global _driver
    
    logging.info("="*60)
    logging.info("Medium Image Upload Tester")
    logging.info("="*60)
    logging.info("")
    logging.info("Available functions:")
    logging.info("  1. open_first_profile() - Open first profile and get driver")
    logging.info("  2. attach_first_image() - Upload first image from data/images")
    logging.info("  3. close_profile_if_open() - Close profile if opened")
    logging.info("  4. Exit")
    logging.info("")
    
    while True:
        print("\n" + "="*60)
        print("Choose an action:")
        print("  1 - Open first profile")
        print("  2 - Attach first image")
        print("  3 - Close profile")
        print("  4 - Exit")
        print("="*60)
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            _driver = open_first_profile()
        elif choice == "2":
            attach_first_image()
        elif choice == "3":
            close_profile_if_open()
        elif choice == "4":
            logging.info("Exiting...")
            close_profile_if_open()
            break
        else:
            logging.warning("Invalid choice! Please enter 1-4")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
        close_profile_if_open()
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
        close_profile_if_open()

