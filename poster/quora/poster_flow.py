"""
UI-поток публикации статьи на Quora через PyAutoGUI.
"""
import logging
import pyperclip
from typing import Dict, Optional
from poster.ui.interface import UiDriver
from poster.ui.coords import Coords, Delays
from poster.clipboard.richtext import copy_markdown_as_rich_text
from poster.timing import wait_with_log
from poster.quora.cover_attacher import attach_cover_image
from poster.logging_helper import is_info_mode, log_info_short, log_debug_detailed


def publish_article(
    ui: UiDriver,
    article: Dict,
    coords: Coords,
    delays: Delays,
    driver,  # Selenium WebDriver для прикрепления обложки
    images_root_dir: str = "./data/images",  # Папка с изображениями
    clipboard_copy_rich_text: callable = None
) -> bool:
    """
    Опубликовать статью на Quora через UI.
    
    Args:
        ui: UI драйвер для взаимодействия с экраном
        article: Словарь со статьей (title, body, cover_image_name)
        coords: Координаты для кликов
        delays: Задержки между действиями
        driver: Selenium WebDriver для прикрепления обложки
        images_root_dir: Корневая папка с изображениями
        clipboard_copy_rich_text: Функция для копирования Rich Text (опционально)
    
    Returns:
        True если успешно, False при ошибке
    """
    if clipboard_copy_rich_text is None:
        clipboard_copy_rich_text = copy_markdown_as_rich_text
    
    article_id = article.get('id') if isinstance(article, dict) else article[0]
    
    if isinstance(article, dict):
        title = article.get('title', '').strip()
        quora_text = article.get('quora_text', '').strip()
        cover_image_name = article.get('cover_image_name', '').strip()
    else:
        # Если article - кортеж или именованный кортеж, извлекаем значения
        title = article[2] if len(article) > 2 else ''
        
        # Пробуем получить quora_text по атрибуту (для именованных кортежей)
        quora_text = ''
        cover_image_name = ''
        
        try:
            if hasattr(article, 'quora_text'):
                quora_text = str(article.quora_text).strip() if article.quora_text else ''
            if hasattr(article, 'cover_image_name'):
                cover_image_name = str(article.cover_image_name).strip() if article.cover_image_name else ''
        except AttributeError:
            pass
        
        # Если не получилось по атрибуту, пробуем по индексу
        # quora_text всегда последний в SELECT (если есть)
        if not quora_text and len(article) > 0:
            last_idx = len(article) - 1
            last_val = article[last_idx]
            if last_val:
                quora_text = str(last_val).strip()
        
        # cover_image_name предпоследний (если quora_text есть и есть cover_image_name)
        if not cover_image_name and len(article) > 1:
            # Если quora_text найден, cover_image_name может быть предпоследним
            if quora_text and len(article) > 1:
                prev_idx = len(article) - 2
                prev_val = article[prev_idx]
                if prev_val:
                    cover_image_name = str(prev_val).strip()
    
    # Проверяем наличие quora_text - обязательное требование для постинга на Quora
    if not quora_text:
        logging.error("=" * 60)
        logging.error("ERROR: Article ID %s has empty quora_text column!", article_id)
        logging.error("Quora text is required for posting to Quora.")
        logging.error("Please run quora_text_edit.py to generate quora_text for this article.")
        logging.error("Skipping this article and moving to the next one.")
        logging.error("=" * 60)
        return False

    if is_info_mode():
        log_info_short(f"Статья: {title[:50]}{'...' if len(title) > 50 else ''}, обложка: {cover_image_name if cover_image_name else 'нет'}")
    else:
        logging.info("Article title: %s", title[:50] + "..." if len(title) > 50 else title)
        logging.info("Quora text length: %d characters", len(quora_text))
        logging.info("Cover image: %s", cover_image_name if cover_image_name else "None")
        logging.info("")

    # STEP 1: Wait after opening tab (already done in tab manager)
    log_debug_detailed("STEP 1: Waiting after opening Quora tab...")
    wait_with_log(delays.QUORA_AFTER_OPEN_TAB, "STEP 1", 10.0)

    # STEP 2: Empty click to guarantee focus
    if is_info_mode():
        log_info_short("Клик 1: Пустой клик для фокуса")
    else:
        logging.info("STEP 2: Empty click to guarantee focus...")
        logging.info("  Coordinates: %s", coords.QUORA_EMPTY_CLICK)
    try:
        ui.click(*coords.QUORA_EMPTY_CLICK)
        log_debug_detailed("  ✓ Empty click successful")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_EMPTY_CLICK, "STEP 2", 10.0)

    # STEP 3: Click Create post button
    if is_info_mode():
        log_info_short("Клик 2: Кнопка Create post")
    else:
        logging.info("STEP 3: Clicking Create post button...")
        logging.info("  Coordinates: %s", coords.QUORA_CREATE_POST)
    try:
        ui.screenshot_on_click(coords.QUORA_CREATE_POST, label="STEP 3: create post click")
        ui.sleep(1)
        ui.click(*coords.QUORA_CREATE_POST)
        log_debug_detailed("  ✓ Create post clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_CREATE_POST, "STEP 3", 10.0)

    # STEP 4: Click on text field button
    if is_info_mode():
        log_info_short("Клик 3: Текстовое поле")
    else:
        logging.info("STEP 4: Clicking on text field button...")
        logging.info("  Coordinates: %s", coords.QUORA_TEXT_FIELD)
    try:
        ui.screenshot_on_click(coords.QUORA_TEXT_FIELD, label="STEP 4: text field click")
        ui.sleep(1)
        ui.click(*coords.QUORA_TEXT_FIELD)
        log_debug_detailed("  ✓ Text field clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_TEXT_FIELD, "STEP 4", 10.0)

    # STEP 5: Enter article title
    if is_info_mode():
        log_info_short("Вставка заголовка")
    else:
        logging.info("STEP 5: Entering article title...")
        logging.info("  Title length: %d characters", len(title))
    try:
        # Очищаем поле перед вставкой (Ctrl+A, затем Delete)
        log_debug_detailed("  Clearing text field...")
        ui.hotkey('ctrl', 'a')
        ui.sleep(1)
        ui.press('delete')
        ui.sleep(1)
        
        # Копируем и вставляем title
        log_debug_detailed("  Copying title to clipboard...")
        pyperclip.copy(title)
        ui.sleep(1)
        log_debug_detailed("  Pasting title...")
        ui.hotkey('ctrl', 'v')
        log_debug_detailed("  ✓ Title pasted successfully")
        ui.sleep(1)
    except Exception as e:
        logging.error("  ✗ Failed to paste title: %s", e)
        return False

    # STEP 6: Press Enter
    if is_info_mode():
        log_info_short("Нажатие Enter")
    else:
        logging.info("STEP 6: Pressing Enter...")
    try:
        ui.press('enter')
        log_debug_detailed("  ✓ Enter pressed successfully")
        ui.sleep(1)
    except Exception as e:
        logging.error("  ✗ Failed to press Enter: %s", e)
        return False

    # STEP 7: Enter article body (using quora_text)
    if is_info_mode():
        log_info_short("Вставка тела статьи (Quora текст)")
    else:
        logging.info("STEP 7: Entering article body (quora_text)...")
        logging.info("  Quora text length: %d characters", len(quora_text))
    try:
        log_debug_detailed("  Converting Markdown to HTML and placing to clipboard as CF_HTML...")
        if not clipboard_copy_rich_text(quora_text):
            log_debug_detailed("  Failed to copy as Rich Text, falling back to plain text")
            pyperclip.copy(quora_text)

        ui.sleep(0.5)
        ui.hotkey('ctrl', 'v')
        ui.sleep(1)
        log_debug_detailed("  ✓ Quora text pasted successfully")
    except Exception as e:
        logging.error("  ✗ Failed to paste quora_text: %s", e, exc_info=True)
        return False

    # STEP 8: Click on image upload button
    if is_info_mode():
        log_info_short("Клик 4: Кнопка загрузки изображения")
    else:
        logging.info("STEP 8: Clicking on image upload button...")
        logging.info("  Coordinates: %s", coords.QUORA_IMAGE_UPLOAD)
    try:
        ui.screenshot_on_click(coords.QUORA_IMAGE_UPLOAD, label="STEP 8: image upload click")
        ui.sleep(1)
        ui.click(*coords.QUORA_IMAGE_UPLOAD)
        ui.sleep(1)
        ui.press('esc')
        log_debug_detailed("  ✓ Image upload button clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    # STEP 9: Attach cover image via Selenium
    if cover_image_name and driver:
        if is_info_mode():
            log_info_short(f"Прикрепление обложки: {cover_image_name}")
        else:
            logging.info("STEP 9: Attaching cover image...")
            logging.info("  Cover image name: %s", cover_image_name)
        try:
            success = attach_cover_image(
                driver=driver,
                cover_image_name=cover_image_name,
                images_root_dir=images_root_dir,
                article_id=article_id
            )
            if not success:
                log_debug_detailed("  ⚠ Failed to attach cover image, continuing without it")
            else:
                if is_info_mode():
                    log_info_short("✓ Обложка прикреплена")
                else:
                    logging.info("  ✓ Cover image attached successfully")
        except Exception as e:
            logging.error("  ✗ Error attaching cover image: %s", e, exc_info=True)
            log_debug_detailed("  Continuing without cover image...")
    elif cover_image_name and not driver:
        log_debug_detailed(f"STEP 9: Cover image specified ({cover_image_name}) but no driver available, skipping...")
    else:
        log_debug_detailed("STEP 9: No cover image specified, skipping...")

    wait_with_log(delays.QUORA_AFTER_IMAGE_UPLOAD, "STEP 9", 10.0)

    # STEP 10: Click Post button
    if is_info_mode():
        log_info_short("Клик 5: Кнопка Post")
    else:
        logging.info("STEP 10: Clicking Post button...")
        logging.info("  Coordinates: %s", coords.QUORA_POST_BUTTON)
    try:
        ui.screenshot_on_click(coords.QUORA_POST_BUTTON, label="STEP 10: post click")
        ui.sleep(1)
        ui.click(*coords.QUORA_POST_BUTTON)
        log_debug_detailed("  ✓ Post button clicked successfully")
        ui.sleep(5)
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_POST, "STEP 10", 10.0)
    if is_info_mode():
        log_info_short("✓ Публикация завершена")
    else:
        logging.info("  ✓ Publication should be complete")
    return True
