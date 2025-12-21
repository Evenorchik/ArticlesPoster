"""
Модуль прикрепления обложки статьи на Medium.
"""
import os
import logging
import time
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# Константы
MAX_BYTES = 2_200_000  # ~2MB
ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
FILE_INPUT_CSS_SELECTORS = [
    'input[type="file"][name="uploadedFile"]',  # Medium specific
    'input[type="file"][accept*="image"]',
    'input[type="file"]',
]
WAIT_INPUT_TIMEOUT_SEC = 20
WAIT_UPLOAD_TIMEOUT_SEC = 60


def resolve_cover_image_path(cover_image_name: str, images_root_dir: str) -> tuple:
    """
    Резолвит абсолютный путь к файлу обложки.
    
    Args:
        cover_image_name: Имя файла обложки (например, cover_image_1.jpg)
        images_root_dir: Корневая папка с изображениями
    
    Returns:
        (success, abs_path, error_code)
    """
    # Нормализация имени файла (защита от path traversal)
    if not cover_image_name:
        return False, None, "FILE_KEY_INVALID"
    
    # Запрещаем .., /, \ в имени файла
    if '..' in cover_image_name or '/' in cover_image_name or '\\' in cover_image_name:
        logging.error("  ✗ Invalid cover_image_name (contains path traversal): %s", cover_image_name)
        return False, None, "FILE_KEY_INVALID"
    
    # Собираем путь
    abs_path = os.path.abspath(os.path.join(images_root_dir, cover_image_name))
    
    # Проверяем существование файла
    if not os.path.exists(abs_path):
        logging.error("  ✗ Cover image file not found: %s", abs_path)
        return False, None, "FILE_NOT_FOUND"
    
    # Проверяем, что это файл, а не папка
    if not os.path.isfile(abs_path):
        logging.error("  ✗ Cover image path is not a file: %s", abs_path)
        return False, None, "FILE_NOT_FOUND"
    
    # Проверяем расширение
    _, ext = os.path.splitext(abs_path)
    ext_lower = ext.lower()
    if ext_lower not in ALLOWED_EXT:
        logging.error("  ✗ Cover image has invalid extension: %s (allowed: %s)", ext_lower, ALLOWED_EXT)
        return False, None, "FILE_BAD_EXTENSION"
    
    # Проверяем размер
    file_size = os.path.getsize(abs_path)
    if file_size > MAX_BYTES:
        logging.error("  ✗ Cover image file too large: %d bytes (max: %d)", file_size, MAX_BYTES)
        return False, None, "FILE_TOO_LARGE"
    
    logging.info("  ✓ Cover image resolved: %s (%d bytes)", abs_path, file_size)
    return True, abs_path, None


def attach_cover_image(
    driver,
    cover_image_name: str,
    images_root_dir: str = "./data/images",
    article_id: Optional[int] = None
) -> bool:
    """
    Прикрепить обложку статьи на Medium через Selenium.
    
    Args:
        driver: Selenium WebDriver
        cover_image_name: Имя файла обложки
        images_root_dir: Корневая папка с изображениями
        article_id: ID статьи (для логирования)
    
    Returns:
        True если успешно, False при ошибке
    """
    if not cover_image_name:
        logging.warning("  ⚠ No cover_image_name provided, skipping cover attachment")
        return False
    
    # Резолвим путь к файлу
    success, abs_path, error_code = resolve_cover_image_path(cover_image_name, images_root_dir)
    if not success:
        logging.error("  ✗ Failed to resolve cover image path: %s", error_code)
        return False
    
    try:
        # Ищем input[type="file"]
        file_input = None
        for selector in FILE_INPUT_CSS_SELECTORS:
            try:
                wait = WebDriverWait(driver, WAIT_INPUT_TIMEOUT_SEC)
                file_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                # Проверяем, что элемент доступен (может быть скрыт, но это нормально для Medium)
                if file_input.is_enabled():
                    logging.info("  ✓ Found file input with selector: %s", selector)
                    break
            except TimeoutException:
                logging.debug("  Selector %s did not find input, trying next...", selector)
                continue
        
        if not file_input:
            logging.error("  ✗ File input not found with any selector")
            return False
        
        # Прикрепляем файл
        logging.info("  Sending file path to input: %s", abs_path)
        file_input.send_keys(abs_path)
        
        # Даем время на обработку файла Medium
        logging.info("  Waiting for Medium to process the file...")
        time.sleep(3)  # Даем время на загрузку и обработку
        
        logging.info("  ✓ Cover image attached successfully")
        return True
        
    except Exception as e:
        logging.error("  ✗ Failed to attach cover image: %s", e, exc_info=True)
        return False

