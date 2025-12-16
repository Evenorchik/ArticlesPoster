"""
CLI для ручного постинга статей на Medium.
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
    PROFILE_SEQUENTIAL_MAPPING,
    get_profile_no,
    get_profile_id_by_sequential_no,
    get_profile_no_by_sequential_no,
)
from poster.models import Profile
from poster.adspower.api_client import AdsPowerApiClient
from poster.adspower.profile_manager import ProfileManager
from poster.adspower.window_manager import WindowManager
from poster.adspower.tabs import TabManager
from poster.ui import PyAutoGuiDriver, Coords, Delays
from poster.medium import publish_article, fetch_published_url
from poster.timing import random_delay

# Logs
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def open_and_maximize_profile(
    sequential_no: int,
    profile_manager: ProfileManager,
    window_manager: WindowManager,
    tab_manager: TabManager,
    ui: PyAutoGuiDriver
) -> Profile:
    """
    Открывает и подготавливает профиль по sequential_no (1-10) так, как нужно для PyAutoGUI.
    """
    logging.info("=" * 60)
    logging.info("Opening profile with sequential_no: %d", sequential_no)
    logging.info("=" * 60)

    profile_id = get_profile_id_by_sequential_no(sequential_no)
    if not profile_id:
        logging.error("Profile with sequential_no %d not found", sequential_no)
        return None

    profile_no = get_profile_no_by_sequential_no(sequential_no)
    if not profile_no:
        logging.error("Profile_no not found for sequential_no %d", sequential_no)
        return None

    logging.info("Profile info: %s (No: %s, Seq: %s)", profile_id, profile_no, sequential_no)

    profile = profile_manager.ensure_ready(profile_no)
    if not profile:
        logging.error("Failed to ensure profile %d is ready", profile_no)
        return None

    # Фокус/максимизация окна (безопасно и без ошибок)
    if not window_manager.focus(profile):
        logging.warning("Failed to focus/maximize window, but continuing...")

    # Medium вкладка должна быть активна на экране
    if not tab_manager.ensure_medium_tab_open(profile, ui, window_manager):
        logging.error("Failed to open Medium tab for profile %d", profile_no)
        return None

    logging.info("=" * 60)
    logging.info("✓ Profile ready: window focused, Medium tab active")
    logging.info("=" * 60)
    return profile


def main():
    """Основная функция CLI."""
    logging.info("="*60)
    logging.info("Starting Medium Poster Script (PyAutoGUI + Ads Power)")
    logging.info("="*60)

    logging.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn()

    try:
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

        ensure_profile_id_column(pg_conn, selected_table)

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
        logging.info("")

        response = input(f"Ready to post {len(unpublished_articles)} article(s). Press Enter to start, or 'q' to quit: ").strip().lower()
        if response == 'q':
            logging.info("Aborted by user")
            return

        sequential_index = 0
        if not PROFILE_SEQUENTIAL_MAPPING:
            logging.error("PROFILE_SEQUENTIAL_MAPPING is empty! Cannot proceed.")
            return

        max_sequential_no = max(PROFILE_SEQUENTIAL_MAPPING.values())
        if max_sequential_no <= 0:
            logging.error("Invalid max_sequential_no: %d. Must be > 0", max_sequential_no)
            return

        # Инициализация компонентов
        api_client = AdsPowerApiClient()
        profile_manager = ProfileManager(api_client)
        window_manager = WindowManager()
        tab_manager = TabManager()
        ui = PyAutoGuiDriver()
        coords = Coords()
        delays = Delays()

        posted_count = 0
        failed_count = 0

        for article in unpublished_articles:
            article_id = article.get('id') if isinstance(article, dict) else article[0]

            sequential_no = (sequential_index % max_sequential_no) + 1
            sequential_index += 1

            logging.info("")
            logging.info("="*60)
            logging.info("Processing article ID %s with profile sequential_no: %d", article_id, sequential_no)
            logging.info("="*60)

            profile = open_and_maximize_profile(
                sequential_no,
                profile_manager,
                window_manager,
                tab_manager,
                ui
            )
            if not profile:
                logging.error("Failed to open profile with sequential_no %d, skipping article ID %s", sequential_no, article_id)
                failed_count += 1
                continue

            profile_no = profile.profile_no
            profile_id = profile.profile_id
            profile_info = f"{profile_id} (No: {profile_no}, Seq: {sequential_no})"
            logging.info("Profile ready: %s", profile_info)

            time.sleep(2)

            try:
                # Публикация статьи
                success = publish_article(ui, article, coords, delays)
                
                if success:
                    # Получаем URL
                    url = fetch_published_url(profile, ui)
                    
                    if url:
                        update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                        posted_count += 1
                        logging.info("✓ Article ID %s posted successfully!", article_id)

                        window_manager.minimize(profile)
                        time.sleep(1)

                        logging.info("Closing profile after successful post...")
                        profile_manager.close(profile_no)

                        time.sleep(2)
                    else:
                        failed_count += 1
                        logging.error("✗ Failed to get URL for article ID %s", article_id)
                        window_manager.minimize(profile)
                else:
                    failed_count += 1
                    logging.error("✗ Failed to post article ID %s", article_id)
                    window_manager.minimize(profile)

            except Exception as e:
                logging.error("Error during posting process: %s", e, exc_info=True)
                failed_count += 1
                window_manager.minimize(profile)

            if article != unpublished_articles[-1]:
                pause_time = random_delay(5.0, 10.0)
                logging.info("Waiting %.2f seconds before next article...", pause_time)
                time.sleep(pause_time)

        logging.info("")
        logging.info("="*60)
        logging.info("Posting completed!")
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
    main()

