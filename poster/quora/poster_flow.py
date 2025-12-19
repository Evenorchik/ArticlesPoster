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
        body = article.get('body', '').strip()
        cover_image_name = article.get('cover_image_name', '').strip()
    else:
        title = article[2] if len(article) > 2 else ''
        body = article[3] if len(article) > 3 else ''
        cover_image_name = article[9] if len(article) > 9 else ''  # Предполагаем, что cover_image_name в индексе 9

    logging.info("Article title: %s", title[:50] + "..." if len(title) > 50 else title)
    logging.info("Article body length: %d characters", len(body))
    logging.info("Cover image: %s", cover_image_name if cover_image_name else "None")
    logging.info("")

    # STEP 1: Wait after opening tab (already done in tab manager)
    logging.info("STEP 1: Waiting after opening Quora tab...")
    wait_with_log(delays.QUORA_AFTER_OPEN_TAB, "STEP 1", 10.0)

    # STEP 2: Empty click to guarantee focus
    logging.info("STEP 2: Empty click to guarantee focus...")
    logging.info("  Coordinates: %s", coords.QUORA_EMPTY_CLICK)
    try:
        ui.click(*coords.QUORA_EMPTY_CLICK)
        logging.info("  ✓ Empty click successful")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_EMPTY_CLICK, "STEP 2", 10.0)

    # STEP 3: Click Create post button
    logging.info("STEP 3: Clicking Create post button...")
    logging.info("  Coordinates: %s", coords.QUORA_CREATE_POST)
    try:
        ui.screenshot_on_click(coords.QUORA_CREATE_POST, label="STEP 3: create post click")
        ui.sleep(1)
        ui.click(*coords.QUORA_CREATE_POST)
        logging.info("  ✓ Create post clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_CREATE_POST, "STEP 3", 10.0)

    # STEP 4: Click on text field button
    logging.info("STEP 4: Clicking on text field button...")
    logging.info("  Coordinates: %s", coords.QUORA_TEXT_FIELD)
    try:
        ui.screenshot_on_click(coords.QUORA_TEXT_FIELD, label="STEP 4: text field click")
        ui.sleep(1)
        ui.click(*coords.QUORA_TEXT_FIELD)
        logging.info("  ✓ Text field clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_TEXT_FIELD, "STEP 4", 10.0)

    # STEP 5: Enter article title
    logging.info("STEP 5: Entering article title...")
    logging.info("  Title length: %d characters", len(title))
    try:
        # Очищаем поле перед вставкой (Ctrl+A, затем Delete)
        logging.info("  Clearing text field...")
        ui.hotkey('ctrl', 'a')
        ui.sleep(1)
        ui.press('delete')
        ui.sleep(1)
        
        # Копируем и вставляем title
        logging.info("  Copying title to clipboard...")
        pyperclip.copy(title)
        ui.sleep(1)
        logging.info("  Pasting title...")
        ui.hotkey('ctrl', 'v')
        logging.info("  ✓ Title pasted successfully")
        ui.sleep(1)
    except Exception as e:
        logging.error("  ✗ Failed to paste title: %s", e)
        return False

    # STEP 6: Press Enter
    logging.info("STEP 6: Pressing Enter...")
    try:
        ui.press('enter')
        logging.info("  ✓ Enter pressed successfully")
        ui.sleep(1)
    except Exception as e:
        logging.error("  ✗ Failed to press Enter: %s", e)
        return False

    # STEP 7: Enter article body
    logging.info("STEP 7: Entering article body...")
    logging.info("  Body length: %d characters", len(body))
    try:
        logging.debug("  Converting Markdown to HTML and placing to clipboard as CF_HTML...")
        if not clipboard_copy_rich_text(body):
            logging.warning("  Failed to copy as Rich Text, falling back to plain text")
            pyperclip.copy(body)

        ui.sleep(0.5)
        ui.hotkey('ctrl', 'v')
        ui.sleep(1)
        logging.info("  ✓ Body pasted successfully")
    except Exception as e:
        logging.error("  ✗ Failed to paste body: %s", e, exc_info=True)
        return False

    # STEP 8: Click on image upload button
    # ЗАКОММЕНТИРОВАНО: Пропускаем клик на кнопку, input уже есть в DOM
    # logging.info("STEP 8: Clicking on image upload button...")
    # logging.info("  Coordinates: %s", coords.QUORA_IMAGE_UPLOAD)
    # try:
    #     ui.screenshot_on_click(coords.QUORA_IMAGE_UPLOAD, label="STEP 8: image upload click")
    #     ui.sleep(1)
    #     ui.click(*coords.QUORA_IMAGE_UPLOAD)
    #     logging.info("  ✓ Image upload button clicked successfully")
    # except Exception as e:
    #     logging.error("  ✗ Failed to click: %s", e)
    #     return False
    logging.info("STEP 8: Skipping image upload button click (input already in DOM)")

    # STEP 9: Attach cover image via Selenium
    if cover_image_name:
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
                logging.warning("  ⚠ Failed to attach cover image, continuing without it")
            else:
                logging.info("  ✓ Cover image attached successfully")
        except Exception as e:
            logging.error("  ✗ Error attaching cover image: %s", e, exc_info=True)
            logging.warning("  Continuing without cover image...")
    else:
        logging.info("STEP 9: No cover image specified, skipping...")

    wait_with_log(delays.QUORA_AFTER_IMAGE_UPLOAD, "STEP 9", 10.0)

    # STEP 10: Click Post button
    logging.info("STEP 10: Clicking Post button...")
    logging.info("  Coordinates: %s", coords.QUORA_POST_BUTTON)
    try:
        ui.screenshot_on_click(coords.QUORA_POST_BUTTON, label="STEP 10: post click")
        ui.sleep(1)
        ui.click(*coords.QUORA_POST_BUTTON)
        logging.info("  ✓ Post button clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.QUORA_AFTER_POST, "STEP 10", 10.0)
    logging.info("  ✓ Publication should be complete")
    return True

