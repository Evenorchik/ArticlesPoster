"""
UI-поток публикации статьи на Quora через PyAutoGUI.
"""
import time
import logging
import pyperclip
from typing import Dict, List, Optional
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
    driver: Optional[object] = None,
    images_root_dir: str = "./data/images",
    clipboard_copy_rich_text: callable = None
) -> bool:
    """
    Опубликовать статью на Quora через UI.
    
    Args:
        ui: UI драйвер для взаимодействия с экраном
        article: Словарь со статьей (title, body, hashtags, cover_image_name)
        coords: Координаты для кликов
        delays: Задержки между действиями
        driver: Selenium WebDriver для загрузки обложки (опционально)
        images_root_dir: Папка с изображениями обложек (по умолчанию "./data/images")
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
        hashtags = [
            article.get('hashtag1', '').strip(),
            article.get('hashtag2', '').strip(),
            article.get('hashtag3', '').strip(),
            article.get('hashtag4', '').strip(),
            article.get('hashtag5', '').strip() if article.get('hashtag5') else ''
        ]
    else:
        title = article[2] if len(article) > 2 else ''
        body = article[3] if len(article) > 3 else ''
        hashtags = [
            article[4] if len(article) > 4 else '',
            article[5] if len(article) > 5 else '',
            article[6] if len(article) > 6 else '',
            article[7] if len(article) > 7 else '',
            article[8] if len(article) > 8 else ''
        ]

    hashtags = [h for h in hashtags if h]

    logging.info("Article title: %s", title[:50] + "..." if len(title) > 50 else title)
    logging.info("Article body length: %d characters", len(body))
    logging.info("Hashtags: %s", hashtags)
    logging.info("")

    logging.info("STEP 1.1: Reloading the page")
    try:
        ui.sleep(2)
        ui.click(*coords.PUBLISH_BUTTON_1)
        ui.press('f5')
        logging.info("Reloaded")
        ui.sleep(2)
    except Exception as e:
        logging.error("  ✗ Failed to reload: %s", e)
        return False

    logging.info("STEP 1.2: Preparing image upload, we need it for file=input to appear in page code")
    try:
        ui.sleep(2)
        ui.click(*coords.BODY_TEXT)
        logging.info("  ✓ Body clicked")
        ui.sleep(2)
        ui.click(*coords.PLUS_BUTTON)
        logging.info("  ✓ Attach clicked")
        ui.sleep(2)
        ui.click(*coords.IMAGE_BUTTON)
        logging.info("  ✓ Image clicked")
        ui.sleep(2)
        ui.press('esc')
        ui.sleep(2)
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False


    logging.info("STEP 2: Clicking on title input field...")
    logging.info("  Coordinates: %s", coords.TITLE_INPUT)
    try:
        ui.sleep(1)
        ui.screenshot_on_click(coords.TITLE_INPUT, label="STEP 2: title click")
        ui.sleep(2)
        ui.click(*coords.TITLE_INPUT)
        ui.sleep(1)
        ui.click(*coords.TITLE_INPUT)
        logging.info("  ✓ Clicked successfully")
        ui.sleep(1)
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_TITLE_CLICK, "STEP 2", 10.0)

    logging.info("STEP 3: Pasting title...")
    logging.info("  Title length: %d characters", len(title))
    try:
        pyperclip.copy(title)
        ui.sleep(1)
        ui.hotkey('ctrl', 'v')
        logging.info("  ✓ Title pasted successfully")
    except Exception as e:
        logging.error("  ✗ Failed to paste title: %s", e)
        return False

    wait_with_log(delays.AFTER_TITLE_PASTE, "STEP 3", 10.0)

    logging.info("STEP 4: Pressing Enter...")
    try:
        ui.press('enter')
        logging.info("  ✓ Enter pressed successfully")
    except Exception as e:
        logging.error("  ✗ Failed to press Enter: %s", e)
        return False

    wait_with_log(delays.AFTER_ENTER, "STEP 4", 10.0)

    logging.info("STEP 5: Pasting body as Rich Text (HTML via CF_HTML)...")
    logging.info("  Body length: %d characters", len(body))

    ui.sleep(1.5)

    try:
        logging.debug("  Converting Markdown to HTML and placing to clipboard as CF_HTML...")
        if not clipboard_copy_rich_text(body):
            logging.warning("  Failed to copy as Rich Text, falling back to plain text")
            pyperclip.copy(body)

        ui.sleep(0.5)
        ui.hotkey('ctrl', 'v')
        ui.sleep(0.5)
        logging.info("  ✓ Body pasted (via Ctrl+V)")
    except Exception as e:
        logging.error("  ✗ Failed to paste body: %s", e, exc_info=True)
        return False

    wait_with_log(delays.AFTER_BODY_PASTE, "STEP 5", 10.0)

    # Загружаем обложку, если она есть и driver доступен
    cover_image_name = article.get('cover_image_name', '') if isinstance(article, dict) else ''
    if cover_image_name and driver:
        logging.info("STEP 5.1: Attaching cover image: %s", cover_image_name)
        if attach_cover_image(driver, cover_image_name, images_root_dir, article_id):
            logging.info("  ✓ Cover image attached successfully")
        else:
            logging.warning("  ⚠ Failed to attach cover image, but continuing...")
    elif cover_image_name and not driver:
        logging.warning("  ⚠ Cover image name provided (%s) but no driver available, skipping", cover_image_name)
    elif not cover_image_name:
        logging.info("STEP 1.3: No cover image to attach")

    logging.info("STEP 6: Clicking first Publish button...")
    logging.info("  Coordinates: %s", coords.PUBLISH_BUTTON_1)
    logging.info("  Waiting 5 seconds before clicking Publish...")
    ui.sleep(5)
    try:
        ui.sleep(1)
        ui.screenshot_on_click(coords.PUBLISH_BUTTON_1, label="STEP 6: publish 1 click")
        ui.sleep(2)
        ui.click(*coords.PUBLISH_BUTTON_1)
        ui.sleep(1)
        logging.info("  ✓ Clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_PUBLISH_1, "STEP 6", 10.0)

    logging.info("STEP 7: Clicking on hashtags input field...")
    logging.info("  Coordinates: %s", coords.HASHTAGS_INPUT)
    try:
        ui.sleep(1)
        ui.screenshot_on_click(coords.HASHTAGS_INPUT, label="STEP 7: hash click")
        ui.sleep(2)
        ui.click(*coords.HASHTAGS_INPUT)
        ui.sleep(1)
        ui.click(*coords.HASHTAGS_INPUT)
        logging.info("  ✓ Clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_HASHTAGS_CLICK, "STEP 7", 10.0)

    logging.info("STEP 8: Pasting hashtags one by one...")
    logging.info("  Hashtags to paste: %s", hashtags[:5])
    try:
        for i, hashtag in enumerate(hashtags[:5]):
            if hashtag:
                logging.debug("  Pasting hashtag %d/%d: %s", i+1, len(hashtags[:5]), hashtag)
                pyperclip.copy(hashtag)
                ui.sleep(0.2)
                ui.hotkey('ctrl', 'v')
                wait_with_log(delays.BETWEEN_HASHTAGS, f"STEP 8 hashtag {i+1}", 10.0)

                if i < len(hashtags[:5]) - 1:
                    logging.debug("  Adding comma after hashtag %d", i+1)
                    ui.write(',', interval=0.1)
                    wait_with_log(delays.BETWEEN_HASHTAGS, f"STEP 8 comma {i+1}", 10.0)

        logging.info("  ✓ All hashtags pasted successfully")
        logging.info("  Final hashtags: %s", ", ".join(hashtags[:5]))
    except Exception as e:
        logging.error("  ✗ Failed to paste hashtags: %s", e)
        return False

    ui.sleep(1)
    ui.write(',', interval=0.1)
    logging.info("STEP 9: Clicking final Publish button...")
    logging.info("  Coordinates: %s", coords.PUBLISH_BUTTON_2)
    logging.info("  Waiting 3 seconds before clicking final Publish...")
    ui.sleep(3)
    try:
        ui.screenshot_on_click(coords.PUBLISH_BUTTON_2, label="STEP 9: publish 2 click")
        ui.sleep(2)
        ui.click(*coords.PUBLISH_BUTTON_2)
        ui.sleep(1)
        ui.click(*coords.PUBLISH_BUTTON_2_ALT)
        logging.info("  ✓ First click successful")
        ui.sleep(1)
        ui.click(*coords.PUBLISH_BUTTON_2)
        logging.info("  ✓ Second click successful")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_PUBLISH_2, "STEP 9", 10.0)
    logging.info("  ✓ Publication should be complete")
    return True


