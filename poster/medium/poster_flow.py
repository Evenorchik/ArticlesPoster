"""
UI-поток публикации статьи на Medium через PyAutoGUI.
"""
import time
import logging
import pyperclip
from typing import Dict, List
from poster.ui.interface import UiDriver
from poster.ui.coords import Coords, Delays
from poster.clipboard.richtext import copy_markdown_as_rich_text
from poster.timing import wait_with_log
from poster.settings import MEDIUM_NEW_STORY_URL
from poster.logging_helper import is_info_mode, log_info_short, log_debug_detailed


def publish_article(
    ui: UiDriver,
    article: Dict,
    coords: Coords,
    delays: Delays,
    clipboard_copy_rich_text: callable = None
) -> bool:
    """
    Опубликовать статью на Medium через UI.
    
    Args:
        ui: UI драйвер для взаимодействия с экраном
        article: Словарь со статьей (title, body, hashtags)
        coords: Координаты для кликов
        delays: Задержки между действиями
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

    if is_info_mode():
        log_info_short(f"Статья: {title[:50]}{'...' if len(title) > 50 else ''}")
    else:
        logging.info("Article title: %s", title[:50] + "..." if len(title) > 50 else title)
        logging.info("Article body length: %d characters", len(body))
        logging.info("Hashtags: %s", hashtags)
        logging.info("")

    if is_info_mode():
        log_info_short("Клик 1: Перезагрузка страницы")
    else:
        logging.info("STEP 1.1: Reloading the page")
    try:
        ui.sleep(2)
        ui.click(*coords.PUBLISH_BUTTON_1)
        ui.press('f5')
        log_debug_detailed("Reloaded")
        ui.sleep(2)
    except Exception as e:
        logging.error("  ✗ Failed to reload: %s", e)
        return False

    if is_info_mode():
        log_info_short("Клик 2: Поле заголовка")
    else:
        logging.info("STEP 2: Clicking on title input field...")
        logging.info("  Coordinates: %s", coords.TITLE_INPUT)
    try:
        ui.sleep(1)
        ui.screenshot_on_click(coords.TITLE_INPUT, label="STEP 2: title click")
        ui.sleep(2)
        ui.click(*coords.TITLE_INPUT)
        ui.sleep(1)
        ui.click(*coords.TITLE_INPUT)
        log_debug_detailed("  ✓ Clicked successfully")
        ui.sleep(1)
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_TITLE_CLICK, "STEP 2", 10.0)

    if is_info_mode():
        log_info_short("Вставка заголовка")
    else:
        logging.info("STEP 3: Pasting title...")
        logging.info("  Title length: %d characters", len(title))
    try:
        pyperclip.copy(title)
        ui.sleep(1)
        ui.hotkey('ctrl', 'v')
        log_debug_detailed("  ✓ Title pasted successfully")
    except Exception as e:
        logging.error("  ✗ Failed to paste title: %s", e)
        return False

    wait_with_log(delays.AFTER_TITLE_PASTE, "STEP 3", 10.0)

    if is_info_mode():
        log_info_short("Нажатие Enter")
    else:
        logging.info("STEP 4: Pressing Enter...")
    try:
        ui.press('enter')
        log_debug_detailed("  ✓ Enter pressed successfully")
    except Exception as e:
        logging.error("  ✗ Failed to press Enter: %s", e)
        return False

    wait_with_log(delays.AFTER_ENTER, "STEP 4", 10.0)

    if is_info_mode():
        log_info_short("Вставка тела статьи")
    else:
        logging.info("STEP 5: Pasting body as Rich Text (HTML via CF_HTML)...")
        logging.info("  Body length: %d characters", len(body))

    ui.sleep(1.5)

    try:
        log_debug_detailed("  Converting Markdown to HTML and placing to clipboard as CF_HTML...")
        if not clipboard_copy_rich_text(body):
            log_debug_detailed("  Failed to copy as Rich Text, falling back to plain text")
            pyperclip.copy(body)

        ui.sleep(0.5)
        ui.hotkey('ctrl', 'v')
        ui.sleep(0.5)
        log_debug_detailed("  ✓ Body pasted (via Ctrl+V)")
    except Exception as e:
        logging.error("  ✗ Failed to paste body: %s", e, exc_info=True)
        return False

    wait_with_log(delays.AFTER_BODY_PASTE, "STEP 5", 10.0)

    if is_info_mode():
        log_info_short("Клик 3: Первая кнопка Publish")
    else:
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
        log_debug_detailed("  ✓ Clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_PUBLISH_1, "STEP 6", 10.0)

    if is_info_mode():
        log_info_short("Клик 4: Поле хэштегов")
    else:
        logging.info("STEP 7: Clicking on hashtags input field...")
        logging.info("  Coordinates: %s", coords.HASHTAGS_INPUT)
    try:
        ui.sleep(1)
        ui.screenshot_on_click(coords.HASHTAGS_INPUT, label="STEP 7: hash click")
        ui.sleep(2)
        ui.click(*coords.HASHTAGS_INPUT)
        ui.sleep(1)
        ui.click(*coords.HASHTAGS_INPUT)
        log_debug_detailed("  ✓ Clicked successfully")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_HASHTAGS_CLICK, "STEP 7", 10.0)

    if is_info_mode():
        log_info_short("Вставка хэштегов")
    else:
        logging.info("STEP 8: Pasting hashtags one by one...")
        logging.info("  Hashtags to paste: %s", hashtags[:5])
    try:
        for i, hashtag in enumerate(hashtags[:5]):
            if hashtag:
                log_debug_detailed(f"  Pasting hashtag {i+1}/{len(hashtags[:5])}: {hashtag}")
                pyperclip.copy(hashtag)
                ui.sleep(0.2)
                ui.hotkey('ctrl', 'v')
                wait_with_log(delays.BETWEEN_HASHTAGS, f"STEP 8 hashtag {i+1}", 10.0)

                if i < len(hashtags[:5]) - 1:
                    log_debug_detailed(f"  Adding comma after hashtag {i+1}")
                    ui.write(',', interval=0.1)
                    wait_with_log(delays.BETWEEN_HASHTAGS, f"STEP 8 comma {i+1}", 10.0)

        if is_info_mode():
            log_info_short(f"✓ Хэштеги вставлены: {', '.join(hashtags[:5])}")
        else:
            logging.info("  ✓ All hashtags pasted successfully")
            logging.info("  Final hashtags: %s", ", ".join(hashtags[:5]))
    except Exception as e:
        logging.error("  ✗ Failed to paste hashtags: %s", e)
        return False

    if is_info_mode():
        log_info_short("Клик 5: Финальная кнопка Publish")
    else:
        logging.info("STEP 9: Clicking final Publish button...")
        logging.info("  Coordinates: %s", coords.PUBLISH_BUTTON_2)
        logging.info("  Waiting 3 seconds before clicking final Publish...")
    ui.sleep(3)
    try:
        ui.screenshot_on_click(coords.PUBLISH_BUTTON_2, label="STEP 9: publish 2 click")
        ui.sleep(2)
        ui.click(*coords.PUBLISH_BUTTON_2)
        ui.sleep(1)
        log_debug_detailed("  ✓ First click successful")
        ui.sleep(1)
        ui.click(*coords.PUBLISH_BUTTON_2)
        log_debug_detailed("  ✓ Second click successful")
    except Exception as e:
        logging.error("  ✗ Failed to click: %s", e)
        return False

    wait_with_log(delays.AFTER_PUBLISH_2, "STEP 9", 10.0)
    if is_info_mode():
        log_info_short("✓ Публикация завершена")
    else:
        logging.info("  ✓ Publication should be complete")
    return True

