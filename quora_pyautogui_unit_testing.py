"""
Юнит-тестер для PyAutoGUI процесса постинга статей на Quora.

Тестер автоматически:
1. Берет второй профиль из секвенции (sequential_no = 2)
2. Открывает профиль через AdsPower API
3. Максимизирует окно профиля
4. Открывает Quora вкладку
5. Выполняет цикл постинга статей для одного профиля
6. Использует quora_text из базы данных (обязательное требование)
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
from poster.settings import (
    get_profile_id_by_sequential_no,
    get_profile_no_by_sequential_no,
)
from scheduled_poster import (
    open_ads_power_profile,
    post_article_to_quora,
    close_profile,
)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
IMAGES_ROOT_DIR = "./data/images"  # Папка с изображениями для обложек
SEQUENTIAL_NO = 2  # Используем второй профиль из секвенции


def test_quora_pyautogui_posting():
    """
    Основная функция тестера PyAutoGUI процесса для Quora.
    """
    logging.info("="*60)
    logging.info("Quora PyAutoGUI Posting Unit Tester")
    logging.info("="*60)
    logging.info("")
    logging.info("This tester will:")
    logging.info("  - Automatically use second profile from sequence (sequential_no = 2)")
    logging.info("  - Open profile via AdsPower API")
    logging.info("  - Maximize profile window")
    logging.info("  - Open Quora tab")
    logging.info("  - Ask you to select a table and articles from database")
    logging.info("  - Execute full PyAutoGUI posting process for Quora")
    logging.info("  - Use quora_text from database (required, no fallback to body)")
    logging.info("  - Attach cover image if available (via Selenium driver)")
    logging.info("  - Fetch URL and update database")
    logging.info("")
    
    # Получаем второй профиль из секвенции
    sequential_no = SEQUENTIAL_NO
    profile_id = get_profile_id_by_sequential_no(sequential_no)
    profile_no = get_profile_no_by_sequential_no(sequential_no)
    
    if not profile_id or not profile_no:
        logging.error("Failed to get profile for sequential_no=%d", sequential_no)
        logging.error("Make sure PROFILE_SEQUENTIAL_MAPPING is configured correctly")
        return
    
    logging.info("Using profile: sequential_no=%d, profile_no=%d, profile_id=%s", 
                sequential_no, profile_no, profile_id)
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
            quora_text = article.get('quora_text', '') if isinstance(article, dict) else ''
            if not quora_text and not isinstance(article, dict):
                # Пробуем извлечь из кортежа (последний элемент)
                if len(article) > 0:
                    quora_text = str(article[-1]) if article[-1] else ''
            quora_status = f"{len(quora_text.strip())} chars" if quora_text and quora_text.strip() else "⚠ EMPTY"
            logging.info("  %d. ID: %s | Topic: %s | Cover: %s | Quora text: %s", 
                        i, article_id, topic, cover_image, quora_status)
        
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
        
        # Подтверждение перед открытием профиля
        logging.info("")
        logging.info("="*60)
        logging.info("Ready to test Quora PyAutoGUI posting")
        logging.info("  Table: %s", selected_table)
        logging.info("  Articles: %d", len(articles_to_test))
        logging.info("  Profile: No=%d, ID=%s, Seq=%d", profile_no, profile_id, sequential_no)
        logging.info("  Images directory: %s", IMAGES_ROOT_DIR)
        logging.info("="*60)
        logging.info("")
        response = input("Press Enter to open profile and start testing, or 'q' to quit: ").strip().lower()
        if response == 'q':
            logging.info("Aborted by user")
            return
        
        # Открываем профиль и Quora вкладку
        logging.info("")
        logging.info("="*60)
        logging.info("Opening profile and Quora tab...")
        logging.info("="*60)
        profile = open_ads_power_profile(profile_id, platform="quora")
        if not profile:
            logging.error("Failed to open profile! Aborting.")
            return
        
        logging.info("✓ Profile opened and Quora tab is ready")
        time.sleep(3)  # Даем время на загрузку
        
        posted_count = 0
        failed_count = 0
        
        for article in articles_to_test:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            article_topic = article.get('topic', 'N/A')
            cover_image_name = article.get('cover_image_name', '') if isinstance(article, dict) else ''
            quora_text = article.get('quora_text', '') if isinstance(article, dict) else ''
            if not quora_text and not isinstance(article, dict):
                # Пробуем извлечь из кортежа (последний элемент)
                if len(article) > 0:
                    quora_text = str(article[-1]) if article[-1] else ''
            
            logging.info("")
            logging.info("="*60)
            logging.info("Testing Quora PyAutoGUI posting for article ID %s", article_id)
            logging.info("Topic: %s", article_topic[:100] if len(article_topic) > 100 else article_topic)
            if cover_image_name:
                logging.info("Cover image: %s", cover_image_name)
            else:
                logging.info("Cover image: None")
            if quora_text:
                logging.info("Quora text: %d characters", len(quora_text.strip()))
            else:
                logging.warning("⚠ Quora text: EMPTY (article will be skipped with error)")
            logging.info("="*60)
            
            # Небольшая пауза перед началом
            logging.info("Waiting 3 seconds before starting...")
            time.sleep(3)
            
            try:
                # Публикация статьи через функцию из scheduled_poster
                logging.info("")
                logging.info("Posting article to Quora...")
                url = post_article_to_quora(article, profile_id)
                
                if url:
                    logging.info("✓ Article ID %s posted to Quora successfully! URL: %s", article_id, url)
                    
                    # Обновление БД
                    logging.info("")
                    logging.info("Updating database...")
                    try:
                        update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                        posted_count += 1
                        logging.info("✓ Article ID %s saved to database!", article_id)
                    except Exception as e:
                        logging.error("✗ Failed to update database: %s", e, exc_info=True)
                        failed_count += 1
                else:
                    logging.error("✗ Failed to post article ID %s to Quora", article_id)
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
        
        # Закрываем профиль после завершения
        logging.info("")
        logging.info("Closing profile...")
        close_profile(profile_id)
        logging.info("✓ Profile closed")
        
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
        # Закрываем профиль при прерывании
        try:
            close_profile(profile_id)
        except Exception:
            pass
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
        # Закрываем профиль при ошибке
        try:
            close_profile(profile_id)
        except Exception:
            pass
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    test_quora_pyautogui_posting()

