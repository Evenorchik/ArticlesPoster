"""
Модуль для автоматического постинга статей на Medium по расписанию.
Логика:
- Четные дни → профили 1-5
- Нечетные дни → профили 6-10
- Время постинга: 8-13 GMT-5 (случайное для каждого профиля)
- В день: 4 статьи is_link='no' и 1 статья is_link='yes'
"""
import time
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import pytz

# Импортируем функции из medium_poster
from medium_poster import (
    get_pg_conn,
    get_refined_articles_tables,
    get_profile_no,
    get_profile_id,
    get_sequential_no,
    PROFILE_SEQUENTIAL_MAPPING,
    PROFILE_IDS,
    PROFILE_MAPPING,
    open_ads_power_profile,
    post_article_to_medium,
    update_article_url_and_profile,
    minimize_profile_window,
    close_profile,
    ensure_profile_id_column,
)
from config import LOG_LEVEL, LOG_MODE
from psycopg import sql
from telegram_bot import notify_poster_started, notify_article_posted

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
GMT_MINUS_5 = pytz.timezone('America/New_York')  # GMT-5 (EST/EDT)
<<<<<<< HEAD
POSTING_START_HOUR = 00.1   # 19:30 (19 + 30/60 = 19.5)
POSTING_END_HOUR = 02.0   # 20:20 (20 + 20/60 = 20.333...)
=======
POSTING_START_HOUR = 19.5   # 19:30 (19 + 30/60 = 19.5)
POSTING_END_HOUR = 20.333   # 20:20 (20 + 20/60 = 20.333...)
>>>>>>> d48d2828e08feb87b16238a540b3a9a9fb11a464
ARTICLES_NO_LINK_COUNT = 4  # Статей с is_link='no' в день
ARTICLES_WITH_LINK_COUNT = 1  # Статей с is_link='yes' в день


def get_articles_by_is_link(pg_conn, table_name: str, is_link: str, limit: int) -> List[dict]:
    """
    Получает статьи из таблицы с фильтром по is_link.
    Выбирает только неопубликованные статьи (url IS NULL или пустой).
    Возвращает случайный набор статей.
    """
    logging.debug("Fetching articles with is_link='%s' from table %s (limit: %d)", is_link, table_name, limit)
    
    # Проверяем наличие колонки is_link
    check_col_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'is_link'
    """)
    
    with pg_conn.cursor() as cur:
        cur.execute(check_col_query, (table_name,))
        has_is_link = cur.fetchone() is not None
    
    if not has_is_link:
        logging.warning("Column 'is_link' not found in table %s, using default filter", table_name)
        # Если колонки нет, для is_link='no' берем все, для 'yes' - пустой список
        if is_link == 'yes':
            return []
    
    # Проверяем наличие колонки hashtag5
    check_hashtag5_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'hashtag5'
    """)
    
    with pg_conn.cursor() as cur:
        cur.execute(check_hashtag5_query, (table_name,))
        has_hashtag5 = cur.fetchone() is not None
    
    # Формируем запрос в зависимости от наличия hashtag5
    if has_hashtag5:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, hashtag5, url, profile_id, is_link"
    else:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, url, profile_id, is_link"
    
    # Формируем WHERE условие
    if has_is_link:
        query = sql.SQL("""
            SELECT {cols}
            FROM {table}
            WHERE (url IS NULL OR url = '')
            AND is_link = %s
            ORDER BY RANDOM()
            LIMIT %s
        """).format(
            cols=sql.SQL(select_cols),
            table=sql.Identifier(table_name)
        )
        params = (is_link, limit)
    else:
        # Если колонки is_link нет, для 'no' берем все неопубликованные
        query = sql.SQL("""
            SELECT {cols}
            FROM {table}
            WHERE (url IS NULL OR url = '')
            ORDER BY RANDOM()
            LIMIT %s
        """).format(
            cols=sql.SQL(select_cols),
            table=sql.Identifier(table_name)
        )
        params = (limit,)
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, params)
            articles = cur.fetchall()
            logging.info("Fetched %d article(s) with is_link='%s'", len(articles), is_link)
            return articles
    except Exception as e:
        logging.error("Error fetching articles: %s", e)
        raise


def get_profiles_for_today() -> List[Tuple[str, int, int]]:
    """
    Определяет, какие профили использовать сегодня.
    Возвращает список кортежей: (profile_id, profile_no, sequential_no)
    """
    today = datetime.now(GMT_MINUS_5)
    day_of_month = today.day
    is_even_day = (day_of_month % 2 == 0)
    
    if is_even_day:
        # Четный день → профили 1-5
        target_sequential = list(range(1, 6))
        logging.info("Today is even day (%d), using profiles 1-5", day_of_month)
    else:
        # Нечетный день → профили 6-10
        target_sequential = list(range(6, 11))
        logging.info("Today is odd day (%d), using profiles 6-10", day_of_month)
    
    # Находим profile_id и profile_no для каждого sequential_no
    profiles = []
    for seq_no in target_sequential:
        # Ищем profile_no по sequential_no
        for profile_no, seq in PROFILE_SEQUENTIAL_MAPPING.items():
            if seq == seq_no:
                # Находим profile_id по profile_no через PROFILE_MAPPING
                profile_id = None
                for pid, pno in PROFILE_MAPPING.items():
                    if pno == profile_no:
                        profile_id = pid
                        break
                if profile_id:
                    profiles.append((profile_id, profile_no, seq_no))
                break
    
    logging.info("Selected %d profiles for today: %s", len(profiles), 
                [f"Seq:{seq}" for _, _, seq in profiles])
    return profiles


def generate_posting_schedule(profiles: List[Tuple[str, int, int]]) -> List[Tuple[str, int, int, datetime]]:
    """
    Генерирует расписание постинга для профилей.
    Возвращает список: (profile_id, profile_no, sequential_no, posting_time)
    Время выбирается случайно в промежутке 8-13 GMT-5.
    Минимальный интервал между временами постинга - 10 минут.
    """
    today = datetime.now(GMT_MINUS_5).date()
    schedule = []
    used_times = []  # Список уже использованных времен для проверки интервала
    
    for profile_id, profile_no, seq_no in profiles:
        max_attempts = 100  # Максимум попыток генерации времени
        posting_time = None
        
        for attempt in range(max_attempts):
            # Генерируем случайное время между POSTING_START_HOUR и POSTING_END_HOUR
            random_hour = random.uniform(POSTING_START_HOUR, POSTING_END_HOUR)
            hour = int(random_hour)  # Целая часть - часы
            minute = int((random_hour - hour) * 60)  # Дробная часть * 60 = минуты
            
            candidate_time = GMT_MINUS_5.localize(
                datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
            )
            
            # Проверяем, что интервал минимум 10 минут от всех уже использованных времен
            min_interval_ok = True
            for used_time in used_times:
                time_diff = abs((candidate_time - used_time).total_seconds())
                if time_diff < 600:  # 10 минут = 600 секунд
                    min_interval_ok = False
                    break
            
            if min_interval_ok:
                posting_time = candidate_time
                used_times.append(posting_time)
                break
        
        if posting_time is None:
            # Если не удалось найти время с интервалом, используем последнее доступное + 10 минут
            if used_times:
                last_time = max(used_times)
                posting_time = last_time + timedelta(minutes=10)
            else:
                # Первый профиль - случайное время
                random_hour = random.uniform(POSTING_START_HOUR, POSTING_END_HOUR)
                hour = int(random_hour)  # Целая часть - часы
                minute = int((random_hour - hour) * 60)  # Дробная часть * 60 = минуты
                posting_time = GMT_MINUS_5.localize(
                    datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
                )
            used_times.append(posting_time)
            logging.warning("Profile Seq:%d: Could not find time with 10min interval, using %s", 
                          seq_no, posting_time.strftime("%H:%M"))
        
        schedule.append((profile_id, profile_no, seq_no, posting_time))
        logging.info("Profile Seq:%d scheduled for posting at %s (GMT-5)", 
                    seq_no, posting_time.strftime("%H:%M"))
    
    # Сортируем по времени
    schedule.sort(key=lambda x: x[3])
    return schedule


def log_summary(article_topic: str, profile_seq: int, posting_time: datetime, url: str):
    """Сокращенное логирование для режима SUMMARY"""
    if LOG_MODE.upper() == "SUMMARY":
        logging.info("POSTED | Topic: %s | Profile: %d | Time: %s | URL: %s", 
                    article_topic, profile_seq, posting_time.strftime("%H:%M"), url)
    else:
        # В режиме DEBUG уже есть полное логирование
        pass


def wait_until_time(target_time: datetime):
    """Ждет до указанного времени"""
    now = datetime.now(GMT_MINUS_5)
    if target_time <= now:
        logging.warning("Target time %s has already passed, posting immediately", target_time.strftime("%H:%M"))
        return
    
    wait_seconds = (target_time - now).total_seconds()
    logging.info("Waiting until %s (GMT-5) - %.1f seconds remaining", 
                target_time.strftime("%H:%M"), wait_seconds)
    
    # Ждем с периодическими проверками (каждые 60 секунд)
    while datetime.now(GMT_MINUS_5) < target_time:
        remaining = (target_time - datetime.now(GMT_MINUS_5)).total_seconds()
        if remaining > 60:
            time.sleep(60)
            logging.debug("Still waiting... %.1f minutes remaining", remaining / 60)
        else:
            time.sleep(remaining)
            break


def main():
    """Основная функция планировщика"""
    logging.info("="*60)
    logging.info("Starting Scheduled Medium Poster")
    logging.info("Log mode: %s", LOG_MODE.upper())
    logging.info("="*60)
    
    # Подключение к PostgreSQL
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
        
        # Убеждаемся, что колонка profile_id существует в таблице
        ensure_profile_id_column(pg_conn, selected_table)
        
        # Получаем профили для сегодня
        profiles = get_profiles_for_today()
        if not profiles:
            logging.error("No profiles found for today!")
            return
        
        # Генерируем расписание
        schedule = generate_posting_schedule(profiles)
        
        # Получаем статьи
        logging.info("")
        logging.info("Fetching articles from database...")
        articles_no_link = get_articles_by_is_link(pg_conn, selected_table, 'no', ARTICLES_NO_LINK_COUNT)
        articles_with_link = get_articles_by_is_link(pg_conn, selected_table, 'yes', ARTICLES_WITH_LINK_COUNT)
        
        total_articles = len(articles_no_link) + len(articles_with_link)
        logging.info("Total articles to post today: %d (%d with is_link='no', %d with is_link='yes')", 
                    total_articles, len(articles_no_link), len(articles_with_link))
        
        if total_articles == 0:
            logging.warning("No articles to post today!")
            return
        
        if len(articles_no_link) < ARTICLES_NO_LINK_COUNT:
            logging.warning("Only %d articles with is_link='no' available (need %d)", 
                          len(articles_no_link), ARTICLES_NO_LINK_COUNT)
        
        if len(articles_with_link) < ARTICLES_WITH_LINK_COUNT:
            logging.warning("Only %d articles with is_link='yes' available (need %d)", 
                          len(articles_with_link), ARTICLES_WITH_LINK_COUNT)
        
        # Распределяем статьи по профилям
        # Важно: все 5 профилей должны постить, без пересечений
        # 4 профиля постит is_link='no', 1 профиль постит is_link='yes'
        
        random.shuffle(articles_no_link)  # Перемешиваем для случайного распределения
        
        article_assignments = []
        used_profiles = set()  # Множество уже использованных профилей
        
        # Распределяем 4 статьи is_link='no' по первым 4 профилям
        profiles_for_no_link = schedule[:min(len(articles_no_link), len(schedule))]
        
        for i, (profile_id, profile_no, seq_no, posting_time) in enumerate(profiles_for_no_link):
            if i < len(articles_no_link):
                article_assignments.append((profile_id, profile_no, seq_no, posting_time, articles_no_link[i]))
                used_profiles.add(profile_id)  # Отмечаем профиль как использованный
                logging.info("Article is_link='no' (ID: %s) assigned to profile Seq:%d", 
                            articles_no_link[i].get('id'), seq_no)
        
        # Для статьи is_link='yes' выбираем случайный профиль из НЕИСПОЛЬЗОВАННЫХ
        if articles_with_link and len(schedule) > 0:
            article_with_link = articles_with_link[0]
            
            # Находим свободные профили (те, которые не использованы для is_link='no')
            free_profiles = [p for p in schedule if p[0] not in used_profiles]
            
            if free_profiles:
                random_profile = random.choice(free_profiles)  # Случайный профиль из свободных
                article_assignments.append((
                    random_profile[0],  # profile_id
                    random_profile[1],  # profile_no
                    random_profile[2],  # seq_no
                    random_profile[3],  # posting_time
                    article_with_link
                ))
                logging.info("Article with is_link='yes' (ID: %s, Topic: %s) assigned to profile Seq:%d", 
                            article_with_link.get('id'), article_with_link.get('topic', 'N/A')[:50], random_profile[2])
            else:
                logging.error("No free profiles available for article is_link='yes'! All profiles are already used.")
                logging.warning("This should not happen - we have 5 profiles and 5 articles (4+1)")
        
        # Сортируем по времени постинга
        article_assignments.sort(key=lambda x: x[3])
        
        logging.info("")
        logging.info("Posting schedule:")
        for profile_id, profile_no, seq_no, posting_time, article in article_assignments:
            article_topic = article.get('topic', 'N/A')[:50]
            logging.info("  Profile Seq:%d → Article: %s → Time: %s", 
                        seq_no, article_topic, posting_time.strftime("%H:%M"))
        
        # Подтверждение
        logging.info("")
        response = input(f"Ready to post {len(article_assignments)} article(s). Press Enter to start, or 'q' to quit: ").strip().lower()
        if response == 'q':
            logging.info("Aborted by user")
            return
        
        # Отправляем уведомление о запуске автопостера после подтверждения
        try:
            notify_poster_started(selected_table, article_assignments)
        except Exception as e:
            logging.warning("Failed to send Telegram notification about poster start: %s", e)
        
        # Выполняем постинг по расписанию
        posted_count = 0
        failed_count = 0
        
        for profile_id, profile_no, seq_no, posting_time, article in article_assignments:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            article_topic = article.get('topic', 'N/A')
            
            # Ждем до времени постинга
            wait_until_time(posting_time)
            
            # Открываем профиль
            logging.info("")
            logging.info("="*60)
            logging.info("Posting article ID %s (Topic: %s) with profile Seq:%d", 
                        article_id, article_topic[:50], seq_no)
            logging.info("="*60)
            
            result = open_ads_power_profile(profile_id)
            if not result:
                logging.error("Failed to open profile Seq:%d, skipping article ID %s", seq_no, article_id)
                failed_count += 1
                continue
            
            time.sleep(5)
            
            try:
                # Постим статью
                url = post_article_to_medium(article, profile_id)
                
                if url:
                    # Обновляем БД
                    update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                    posted_count += 1
                    
                    # Сокращенное логирование (в режиме SUMMARY)
                    if LOG_MODE.upper() == "SUMMARY":
                        actual_time = datetime.now(GMT_MINUS_5)
                        log_summary(article_topic, seq_no, actual_time, url)
                    else:
                        # В режиме DEBUG уже есть полное логирование из post_article_to_medium
                        logging.info("✓ Article ID %s posted successfully!", article_id)
                    
                    # Отправляем уведомление в Telegram о публикации статьи
                    try:
                        title = article.get('title', '') if isinstance(article, dict) else ''
                        body = article.get('body', '') if isinstance(article, dict) else ''
                        hashtags = [
                            article.get('hashtag1', '').strip() if isinstance(article, dict) else '',
                            article.get('hashtag2', '').strip() if isinstance(article, dict) else '',
                            article.get('hashtag3', '').strip() if isinstance(article, dict) else '',
                            article.get('hashtag4', '').strip() if isinstance(article, dict) else '',
                            article.get('hashtag5', '').strip() if isinstance(article, dict) and article.get('hashtag5') else '',
                        ]
                        hashtags = [h for h in hashtags if h]
                        has_link = article.get('is_link', 'no') == 'yes' if isinstance(article, dict) else False
                        
                        notify_article_posted(
                            title=title,
                            body=body,
                            hashtags=hashtags,
                            url=url,
                            has_link=has_link,
                            profile_no=profile_no,
                            sequential_no=seq_no,
                            profile_id=profile_id
                        )
                    except Exception as e:
                        logging.warning("Failed to send Telegram notification about article: %s", e)
                    
                    # Минимизируем окно перед закрытием
                    minimize_profile_window(profile_no)
                    time.sleep(1)
                    
                    # Закрываем профиль после успешного постинга и сохранения ссылки
                    logging.info("Closing profile after successful post...")
                    close_profile(profile_id)
                    
                    # Небольшая пауза после закрытия профиля
                    time.sleep(2)
                else:
                    failed_count += 1
                    logging.error("✗ Failed to post article ID %s", article_id)
                    
                    # Сворачиваем окно даже при ошибке
                    minimize_profile_window(profile_no)
                    
                    # Не закрываем профиль при ошибке, чтобы можно было проверить проблему
                
            except Exception as e:
                logging.error("Error posting article ID %s: %s", article_id, e, exc_info=True)
                failed_count += 1
                # Минимизируем окно при ошибке
                minimize_profile_window(profile_no)
                # Не закрываем профиль при ошибке
            
            # Пауза между статьями (если не последняя)
            current_article_id = article.get('id') if isinstance(article, dict) else article[0]
            last_article_id = article_assignments[-1][4].get('id') if isinstance(article_assignments[-1][4], dict) else article_assignments[-1][4][0]
            
            if current_article_id != last_article_id:
                pause_time = random.uniform(3.0, 7.0)
                logging.info("Waiting %.1f seconds before next article...", pause_time)
                time.sleep(pause_time)
        
        # Итоги
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

