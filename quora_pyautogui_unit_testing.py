"""
Юнит-тестер для PyAutoGUI процесса постинга статей на Quora.

ВАЖНО: Перед запуском этого тестера убедитесь, что:
1. Профиль AdsPower уже открыт
2. Вкладка Quora уже открыта и активна (https://www.quora.com/)
3. Окно профиля максимизировано
4. Selenium WebDriver подключен к профилю (для прикрепления обложки)

Тестер не открывает профиль, а сразу начинает процесс постинга через PyAutoGUI.
"""
import time
import logging
from config import LOG_LEVEL
from poster.db import (
    get_pg_conn,
    get_refined_articles_tables,
    ensure_profile_id_column,
    parse_id_selection,
    get_articles_to_post,
    update_article_url_and_profile,
)
from poster.ui import PyAutoGuiDriver, Coords, Delays
from poster.quora import publish_article, fetch_published_url
from poster.models import Profile
from poster.settings import get_sequential_no, get_profile_no

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
IMAGES_ROOT_DIR = "./data/images"  # Папка с изображениями для обложек


def get_profile_info_from_user() -> tuple:
    """
    Спрашивает у пользователя информацию о профиле.
    Возвращает (profile_no, profile_id, sequential_no) или None.
    """
    logging.info("")
    logging.info("="*60)
    logging.info("Profile Information")
    logging.info("="*60)
    logging.info("Please enter the profile information for the currently open profile:")
    
    try:
        profile_no_input = input("Enter profile_no (e.g., 70, 74, 80, etc.): ").strip()
        profile_no = int(profile_no_input)
    except ValueError:
        logging.error("Invalid profile_no! Must be a number.")
        return None
    
    try:
        profile_id_input = input("Enter profile_id (AdsPower ID): ").strip()
        if not profile_id_input:
            logging.error("Profile_id cannot be empty!")
            return None
        profile_id = profile_id_input
    except Exception as e:
        logging.error("Error reading profile_id: %s", e)
        return None
    
    # Определяем sequential_no по profile_no
    sequential_no = get_sequential_no(profile_no)
    if not sequential_no:
        logging.warning("Could not determine sequential_no for profile_no %d, using profile_no as sequential_no", profile_no)
        sequential_no = profile_no
    
    logging.info("Profile info: profile_no=%d, profile_id=%s, sequential_no=%d", profile_no, profile_id, sequential_no)
    return (profile_no, profile_id, sequential_no)


def get_selenium_driver_from_user():
    """
    Спрашивает у пользователя, есть ли доступ к Selenium WebDriver.
    Если есть, возвращает driver, иначе None.
    """
    logging.info("")
    logging.info("="*60)
    logging.info("Selenium WebDriver")
    logging.info("="*60)
    logging.info("For attaching cover images, Selenium WebDriver is required.")
    logging.info("If you have the driver connected to the profile, we can use it.")
    logging.info("Otherwise, cover image attachment will be skipped.")
    logging.info("")
    
    response = input("Do you have Selenium WebDriver connected? (y/n, default: n): ").strip().lower()
    if response == 'y':
        # Пытаемся получить driver из открытого профиля
        # В реальном сценарии driver должен быть уже подключен через ProfileManager
        logging.info("Attempting to use existing driver...")
        logging.warning("NOTE: In a real scenario, driver should be connected via ProfileManager.")
        logging.warning("For testing purposes, you may need to manually connect the driver.")
        return None  # В тестере driver обычно None, так как профиль уже открыт
    else:
        logging.info("Skipping cover image attachment (no driver available)")
        return None


def test_quora_pyautogui_posting():
    """
    Основная функция тестера PyAutoGUI процесса для Quora.
    """
    logging.info("="*60)
    logging.info("Quora PyAutoGUI Posting Unit Tester")
    logging.info("="*60)
    logging.info("")
    logging.info("IMPORTANT: Before running this tester, ensure that:")
    logging.info("  1. AdsPower profile is already open")
    logging.info("  2. Quora tab is already open and active")
    logging.info("     (URL should be: https://www.quora.com/)")
    logging.info("  3. Profile window is maximized")
    logging.info("  4. Browser tab with Quora is in focus")
    logging.info("")
    logging.info("This tester will:")
    logging.info("  - Ask you to select a table and article from database")
    logging.info("  - Ask you for profile information (profile_no, profile_id)")
    logging.info("  - Execute full PyAutoGUI posting process for Quora")
    logging.info("  - Attach cover image if available (requires Selenium driver)")
    logging.info("  - Fetch URL using PyAutoGUI fallback (Ctrl+L, Ctrl+C)")
    logging.info("  - Update database with the published URL")
    logging.info("")
    
    response = input("Press Enter to continue, or 'q' to quit: ").strip().lower()
    if response == 'q':
        logging.info("Aborted by user")
        return
    
    # Подключение к PostgreSQL
    logging.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn()
    
    try:
        # Выбор таблицы
        tables = get_refined_articles_tables(pg_conn)
        if not tables:
            logging.error("No refined_articles tables found in database!")
            return
        
        logging.info("")
        logging.info("Available tables:")
        for i, table in enumerate(tables, 1):
            logging.info("  %d. %s", i, table)
        
        table_choice = input("\nEnter table number (or table name): ").strip()
        try:
            table_index = int(table_choice) - 1
            if 0 <= table_index < len(tables):
                selected_table = tables[table_index]
            else:
                logging.error("Invalid table number!")
                return
        except ValueError:
            if table_choice in tables:
                selected_table = table_choice
            else:
                logging.error("Table '%s' not found!", table_choice)
                return
        
        logging.info("Selected table: %s", selected_table)
        
        # Убеждаемся, что колонка profile_id существует
        ensure_profile_id_column(pg_conn, selected_table)
        
        # Выбор статьи
        logging.info("")
        article_selection = input("Enter article IDs (e.g., '1,2,3' or '1-5,10' or leave empty for all unpublished): ").strip()
        
        if article_selection:
            article_ids = parse_id_selection(article_selection)
            logging.info("Selected article IDs: %s", article_ids)
        else:
            article_ids = None
            logging.info("Will fetch all unpublished articles")
        
        articles = get_articles_to_post(pg_conn, selected_table, article_ids)
        
        if not articles:
            logging.warning("No articles to post!")
            return
        
        # Фильтруем только неопубликованные статьи
        unpublished_articles = []
        for article in articles:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            url = article.get('url') if isinstance(article, dict) else (article[-2] if len(article) > 1 else None)
            if not url or url.strip() == '':
                unpublished_articles.append(article)
            else:
                logging.info("Skipping article ID %s (already published: %s)", article_id, url)
        
        if not unpublished_articles:
            logging.warning("All selected articles are already published!")
            return
        
        logging.info("Articles to post: %d", len(unpublished_articles))
        
        # Показываем список статей
        logging.info("")
        logging.info("Available articles:")
        for i, article in enumerate(unpublished_articles, 1):
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            topic = article.get('topic', 'N/A')[:50] if isinstance(article, dict) else 'N/A'
            cover_image = article.get('cover_image_name', 'N/A') if isinstance(article, dict) else 'N/A'
            logging.info("  %d. ID: %s | Topic: %s | Cover: %s", i, article_id, topic, cover_image)
        
        article_choice = input("\nEnter article number to post (or 'all' for all articles): ").strip().lower()
        
        articles_to_test = []
        if article_choice == 'all':
            articles_to_test = unpublished_articles
            logging.info("Selected all %d articles", len(articles_to_test))
        else:
            try:
                article_index = int(article_choice) - 1
                if 0 <= article_index < len(unpublished_articles):
                    articles_to_test = [unpublished_articles[article_index]]
                    article_id = articles_to_test[0].get('id') if isinstance(articles_to_test[0], dict) else articles_to_test[0][0]
                    logging.info("Selected article: ID %s", article_id)
                else:
                    logging.error("Invalid article number!")
                    return
            except ValueError:
                logging.error("Invalid input! Must be a number or 'all'")
                return
        
        # Получаем информацию о профиле
        profile_info = get_profile_info_from_user()
        if not profile_info:
            logging.error("Failed to get profile information!")
            return
        
        profile_no, profile_id, sequential_no = profile_info
        
        # Получаем информацию о Selenium driver
        driver = get_selenium_driver_from_user()
        
        # Подтверждение
        logging.info("")
        logging.info("="*60)
        logging.info("Ready to test Quora PyAutoGUI posting")
        logging.info("  Table: %s", selected_table)
        logging.info("  Articles: %d", len(articles_to_test))
        logging.info("  Profile: No=%d, ID=%s, Seq=%d", profile_no, profile_id, sequential_no)
        logging.info("  Selenium Driver: %s", "Available" if driver else "Not available (cover images will be skipped)")
        logging.info("  Images directory: %s", IMAGES_ROOT_DIR)
        logging.info("="*60)
        logging.info("")
        response = input("Press Enter to start testing, or 'q' to quit: ").strip().lower()
        if response == 'q':
            logging.info("Aborted by user")
            return
        
        # Инициализация компонентов
        ui = PyAutoGuiDriver()
        coords = Coords()
        delays = Delays()
        
        # Создаем минимальный Profile объект для fetch_published_url
        # Примечание: driver может быть None, поэтому fetch_published_url будет использовать PyAutoGUI fallback
        profile = Profile(
            profile_id=profile_id,
            profile_no=profile_no
        )
        # sequential_no и window_tag вычисляются автоматически в __post_init__
        profile.driver = driver  # Может быть None
        profile.quora_window_handle = None
        
        posted_count = 0
        failed_count = 0
        
        for article in articles_to_test:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            article_topic = article.get('topic', 'N/A')
            cover_image_name = article.get('cover_image_name', '') if isinstance(article, dict) else ''
            
            logging.info("")
            logging.info("="*60)
            logging.info("Testing Quora PyAutoGUI posting for article ID %s", article_id)
            logging.info("Topic: %s", article_topic[:100] if len(article_topic) > 100 else article_topic)
            if cover_image_name:
                logging.info("Cover image: %s", cover_image_name)
            else:
                logging.info("Cover image: None")
            logging.info("="*60)
            
            # Небольшая пауза перед началом
            logging.info("Waiting 3 seconds before starting...")
            time.sleep(3)
            
            try:
                # Шаг 1: Публикация статьи через PyAutoGUI
                logging.info("")
                logging.info("STEP 1: Starting Quora PyAutoGUI posting process...")
                success = publish_article(
                    ui=ui,
                    article=article,
                    coords=coords,
                    delays=delays,
                    driver=driver,  # Может быть None
                    images_root_dir=IMAGES_ROOT_DIR
                )
                
                if not success:
                    logging.error("✗ Quora PyAutoGUI posting failed for article ID %s", article_id)
                    failed_count += 1
                    continue
                
                logging.info("✓ Quora PyAutoGUI posting completed successfully")
                
                # Шаг 2: Получение URL (через PyAutoGUI fallback, если driver=None)
                logging.info("")
                logging.info("STEP 2: Fetching published Quora article URL...")
                if not driver:
                    logging.info("  NOTE: Make sure the browser window with Quora is in focus!")
                    logging.info("  The tester will use Ctrl+L and Ctrl+C to copy URL from address bar")
                time.sleep(2)  # Даем время на загрузку страницы
                
                url = fetch_published_url(profile, ui)
                
                if url:
                    logging.info("✓ URL retrieved: %s", url)
                    
                    # Шаг 3: Обновление БД
                    logging.info("")
                    logging.info("STEP 3: Updating database...")
                    try:
                        update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                        posted_count += 1
                        logging.info("✓ Article ID %s posted to Quora and saved successfully!", article_id)
                    except Exception as e:
                        logging.error("✗ Failed to update database: %s", e, exc_info=True)
                        failed_count += 1
                else:
                    logging.error("✗ Failed to get URL for article ID %s", article_id)
                    failed_count += 1
                
            except Exception as e:
                logging.error("Error during Quora posting process: %s", e, exc_info=True)
                failed_count += 1
            
            # Пауза между статьями (если не последняя)
            if article != articles_to_test[-1]:
                pause_time = 5.0
                logging.info("")
                logging.info("Waiting %.1f seconds before next article...", pause_time)
                time.sleep(pause_time)
        
        # Итоги
        logging.info("")
        logging.info("="*60)
        logging.info("Quora PyAutoGUI Testing completed!")
        logging.info("  Posted: %d", posted_count)
        logging.info("  Failed: %d", failed_count)
        logging.info("="*60)
        
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    test_quora_pyautogui_posting()

