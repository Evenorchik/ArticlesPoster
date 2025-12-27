"""
UI-поток публикации статьи на Medium через PyAutoGUI.
"""
import os
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
from poster.medium.cover_attacher import attach_cover_image

PIC_MATCH_CONFIDENCE = 0.95
PIC_HASHTAGS = "./pics_to_click/medium_hashtags.jpg"
PIC_PUBLISH_SECOND = "./pics_to_click/medium_publish_second.jpg"


def publish_article(
    ui: UiDriver,
    article: Dict,
    coords: Coords,
    delays: Delays,
    driver=None,  # Selenium WebDriver для прикрепления обложки
    images_root_dir: str = "./data/images",  # Папка с изображениями
    clipboard_copy_rich_text: callable = None
) -> bool:
    """
    Опубликовать статью на Medium через UI.
    
    Args:
        ui: UI драйвер для взаимодействия с экраном
        article: Словарь со статьей (title, body, hashtags, cover_image_name)
        coords: Координаты для кликов
        delays: Задержки между действиями
        driver: Selenium WebDriver для прикрепления обложки (опционально)
        images_root_dir: Корневая папка с изображениями
        clipboard_copy_rich_text: Функция для копирования Rich Text (опционально)
    
    Returns:
        True если успешно, False при ошибке
    """
    if clipboard_copy_rich_text is None:
        clipboard_copy_rich_text = copy_markdown_as_rich_text
    
    # Проверка наличия картинок для image-based кликов
    missing_images = []
    if not os.path.exists(PIC_HASHTAGS):
        missing_images.append(f"  ✗ {PIC_HASHTAGS}")
    if not os.path.exists(PIC_PUBLISH_SECOND):
        missing_images.append(f"  ✗ {PIC_PUBLISH_SECOND}")
    
    if missing_images:
        logging.error("=" * 60)
        logging.error("ERROR: Required image files for Medium poster are missing!")
        logging.error("The following image files are required but not found:")
        for img in missing_images:
            logging.error(img)
        logging.error("")
        logging.error("Falling back to coordinate-based clicks.")
        logging.error("To enable image-based clicks, please ensure the images exist at:")
        logging.error("  - %s", os.path.abspath(PIC_HASHTAGS))
        logging.error("  - %s", os.path.abspath(PIC_PUBLISH_SECOND))
        logging.error("=" * 60)
    else:
        log_debug_detailed("✓ All required image files found. Image-based clicks enabled.")
    
    article_id = article.get('id') if isinstance(article, dict) else article[0]
    
    if isinstance(article, dict):
        title = article.get('title', '').strip()
        body = article.get('body', '').strip()
        cover_image_name = article.get('cover_image_name', '').strip()
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
        cover_image_name = article[9] if len(article) > 9 else ''  # Предполагаем, что cover_image_name в индексе 9
        hashtags = [
            article[4] if len(article) > 4 else '',
            article[5] if len(article) > 5 else '',
            article[6] if len(article) > 6 else '',
            article[7] if len(article) > 7 else '',
            article[8] if len(article) > 8 else ''
        ]

    hashtags = [h for h in hashtags if h]

    if is_info_mode():
        log_info_short(f"Статья: {title[:50]}{'...' if len(title) > 50 else ''}, обложка: {cover_image_name if cover_image_name else 'нет'}")
    else:
        logging.info("Article title: %s", title[:50] + "..." if len(title) > 50 else title)
        logging.info("Article body length: %d characters", len(body))
        logging.info("Cover image: %s", cover_image_name if cover_image_name else "None")
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
        ui.sleep(2)
        ui.click(*coords.BODY_TEXT)
        ui.sleep(2)
        ui.click(*coords.PLUS_BUTTON)
        ui.sleep(2)
        ui.click(*coords.IMAGE_BUTTON)
        ui.sleep(2)
        ui.press('esc')
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

    # STEP 5.5: Attach cover image (если есть)
    if cover_image_name and driver:
        if is_info_mode():
            log_info_short(f"Прикрепление обложки: {cover_image_name}")
        else:
            logging.info("STEP 5.5: Attaching cover image...")
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
        log_debug_detailed(f"STEP 5.5: Cover image specified ({cover_image_name}) but no driver available, skipping...")
    else:
        log_debug_detailed("STEP 5.5: No cover image specified, skipping...")

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
        # Prefer image-based click (more robust than coordinates). Fallback to coords if not found.
        clicked = False
        if hasattr(ui, "click_image"):
            try:
                log_debug_detailed(f"  Trying image-based click (hashtags), confidence={PIC_MATCH_CONFIDENCE:.2f}, timeout=12s, img={PIC_HASHTAGS}")
                clicked = ui.click_image(PIC_HASHTAGS, confidence=PIC_MATCH_CONFIDENCE, timeout_s=12.0)
                if clicked:
                    log_debug_detailed("  ✓ Image-based click succeeded (hashtags)")
                else:
                    log_debug_detailed("  ⚠ Image-based click did not find a match (hashtags) — falling back to coordinates")
            except Exception:
                log_debug_detailed("  ⚠ Image-based click raised an exception (hashtags) — falling back to coordinates")
                clicked = False
        else:
            log_debug_detailed("  UI driver has no click_image(); using coordinates for hashtags")

        if not clicked:
            ui.screenshot_on_click(coords.HASHTAGS_INPUT, label="STEP 7: hash click (fallback coords)")
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
        # Prefer image-based click for the second publish button. Fallback to coords.
        clicked = False
        center = None
        if hasattr(ui, "locate_center_on_screen"):
            try:
                log_debug_detailed(f"  Locating image for final Publish, confidence={PIC_MATCH_CONFIDENCE:.2f}, timeout=12s, img={PIC_PUBLISH_SECOND}")
                center = ui.locate_center_on_screen(PIC_PUBLISH_SECOND, confidence=PIC_MATCH_CONFIDENCE, timeout_s=12.0)
            except Exception:
                log_debug_detailed("  ⚠ locate_center_on_screen raised an exception — falling back to coordinates")
                center = None
        else:
            log_debug_detailed("  UI driver has no locate_center_on_screen(); using coordinates for final Publish")

        if center:
            ui.click(*center)
            ui.sleep(1)
            log_debug_detailed("  ✓ First click successful (image)")
            ui.sleep(1)
            # Second click (as before), using the same center
            ui.click(*center)
            log_debug_detailed("  ✓ Second click successful (image)")
            clicked = True

        if not clicked:
            ui.screenshot_on_click(coords.PUBLISH_BUTTON_2, label="STEP 9: publish 2 click (fallback coords)")
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

