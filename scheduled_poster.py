"""
Модуль для автоматического постинга статей на Medium по расписанию.
Логика:
- Четные дни → профили 1-5
- Нечетные дни → профили 6-10
- Время постинга: 19:30-20:20 по Киеву (случайное для каждого профиля)
- В день: 4 статьи is_link='no' и 1 статья is_link='yes'
"""
import time
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import pytz

# Импорты из новой модульной архитектуры
from poster.db import (
    get_pg_conn,
    get_refined_articles_tables,
    ensure_profile_id_column,
    update_article_url_and_profile,
)
from poster.settings import (
    PROFILE_SEQUENTIAL_MAPPING,
    PROFILE_IDS,
    PROFILE_MAPPING,
    MEDIUM_NEW_STORY_URL,
    get_profile_no,
    get_profile_id,
    get_sequential_no,
    get_profile_id_by_sequential_no,
    get_profile_no_by_sequential_no,
)
from poster.adspower.api_client import AdsPowerApiClient
from poster.adspower.profile_manager import ProfileManager
from poster.adspower.window_manager import WindowManager
from poster.adspower.tabs import TabManager
from poster.ui import PyAutoGuiDriver, Coords, Delays
from poster.medium import publish_article, fetch_published_url
from poster.models import Profile
from poster.link_replacer import update_article_body_with_replaced_link
from config import LOG_LEVEL, LOG_MODE
from psycopg import sql
from telegram_bot import notify_poster_started, notify_article_posted, notify_posting_complete

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
KIEV_TIMEZONE = pytz.timezone('Europe/Kiev')  # Киевское время (UTC+2/UTC+3)
POSTING_START_HOUR = 19.5   # 19:30 (19 + 30/60 = 19.5)
POSTING_END_HOUR = 20.333   # 20:20 (20 + 20/60 = 20.333...)
ARTICLES_NO_LINK_COUNT = 4  # Статей с is_link='no' в день
ARTICLES_WITH_LINK_COUNT = 1  # Статей с is_link='yes' в день

# Глобальные менеджеры для работы с профилями (инициализируются в main())
_profile_manager: Optional[ProfileManager] = None
_window_manager: Optional[WindowManager] = None
_tab_manager: Optional[TabManager] = None
_ui: Optional[PyAutoGuiDriver] = None
_coords: Optional[Coords] = None
_delays: Optional[Delays] = None


def _init_managers():
    """Инициализирует глобальные менеджеры (вызывается один раз в main())."""
    global _profile_manager, _window_manager, _tab_manager, _ui, _coords, _delays
    if _profile_manager is None:
        api_client = AdsPowerApiClient()
        _profile_manager = ProfileManager(api_client)
        _window_manager = WindowManager()
        _tab_manager = TabManager()
        _ui = PyAutoGuiDriver()
        _coords = Coords()
        _delays = Delays()


def open_ads_power_profile(profile_id: str) -> Optional[Profile]:
    """
    Открывает и подготавливает профиль AdsPower для постинга.
    Возвращает Profile объект или None при ошибке.
    """
    _init_managers()
    
    profile_no = get_profile_no(profile_id)
    if profile_no == 0:
        logging.error("Profile ID %s not found in PROFILE_MAPPING", profile_id)
        return None
    
    sequential_no = get_sequential_no(profile_no)
    if not sequential_no:
        logging.error("Profile No %d has no sequential_no mapping", profile_no)
        return None
    
    logging.info("Opening profile: ID=%s, No=%d, Seq=%d", profile_id, profile_no, sequential_no)
    
    # Подготавливаем профиль
    profile = _profile_manager.ensure_ready(profile_no)
    if not profile:
        logging.error("Failed to ensure profile %d is ready", profile_no)
        return None
    
    # Фокус/максимизация окна
    if not _window_manager.focus(profile):
        logging.warning("Failed to focus/maximize window, but continuing...")
    
    # Открываем Medium вкладку
    if not _tab_manager.ensure_medium_tab_open(profile, _ui, _window_manager):
        logging.error("Failed to open Medium tab for profile %d", profile_no)
        return None
    
    logging.info("✓ Profile ready: window focused, Medium tab active")
    return profile


def post_article_to_medium(article: dict, profile_id: str) -> Optional[str]:
    """
    Публикует статью на Medium через PyAutoGUI.
    Возвращает URL опубликованной статьи или None при ошибке.
    """
    _init_managers()
    
    article_id = article.get('id') if isinstance(article, dict) else article[0]
    profile_no = get_profile_no(profile_id)
    sequential_no = get_sequential_no(profile_no)
    profile_info = f"{profile_id} (No: {profile_no}" + (f", Seq: {sequential_no})" if sequential_no else ")")
    
    logging.info("="*60)
    logging.info("Posting article ID %s using profile: %s", article_id, profile_info)
    logging.info("="*60)
    
    # Получаем профиль из кэша
    if profile_no not in _profile_manager.profiles:
        logging.error("Profile %d not found in profile manager cache", profile_no)
        return None
    
    profile = _profile_manager.profiles[profile_no]
    
    # Убеждаемся, что окно активно и Medium вкладка открыта
    if not _window_manager.focus(profile):
        logging.warning("Failed to focus window, but continuing...")
    
    # Переключаемся на Medium вкладку
    if profile.driver and profile.medium_window_handle:
        try:
            from poster.adspower.tabs import safe_switch_to
            safe_switch_to(profile.driver, profile.medium_window_handle)
            current_url = profile.driver.current_url
            logging.info("Current URL on Medium tab: %s", current_url)
            
            if 'medium.com' not in current_url:
                logging.warning("Not on Medium page, navigating to Medium...")
                profile.driver.get(MEDIUM_NEW_STORY_URL)
                time.sleep(2)
                profile.medium_window_handle = profile.driver.current_window_handle
        except Exception as e:
            logging.warning("Failed to switch to Medium tab: %s, trying to navigate...", e)
            if profile.driver:
                profile.driver.get(MEDIUM_NEW_STORY_URL)
                time.sleep(2)
                profile.medium_window_handle = profile.driver.current_window_handle
    
    # Публикуем статью через PyAutoGUI
    success = publish_article(_ui, article, _coords, _delays)
    if not success:
        logging.error("Failed to publish article ID %s", article_id)
        return None
    
    # Получаем URL опубликованной статьи
    time.sleep(2)  # Даем время на загрузку страницы
    url = fetch_published_url(profile, _ui)
    
    if url:
        logging.info("✓ Article published successfully! URL: %s", url)
        return url
    else:
        logging.error("Failed to get URL for article ID %s", article_id)
        return None


def minimize_profile_window(profile_no: int) -> bool:
    """Минимизирует окно профиля."""
    _init_managers()
    
    if profile_no not in _profile_manager.profiles:
        logging.warning("Profile %d not found in profile manager cache", profile_no)
        return False
    
    profile = _profile_manager.profiles[profile_no]
    return _window_manager.minimize(profile)


def close_profile(profile_id: str) -> bool:
    """Закрывает профиль AdsPower."""
    _init_managers()
    
    profile_no = get_profile_no(profile_id)
    if profile_no == 0:
        logging.error("Profile ID %s not found in PROFILE_MAPPING", profile_id)
        return False
    
    return _profile_manager.close(profile_no)


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
    today = datetime.now(KIEV_TIMEZONE)
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
    Время выбирается случайно в промежутке 19:30-20:20 по Киеву.
    Минимальный интервал между временами постинга - 10 минут.
    """
    today = datetime.now(KIEV_TIMEZONE).date()
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
            
            candidate_time = KIEV_TIMEZONE.localize(
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
                posting_time = KIEV_TIMEZONE.localize(
                    datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
                )
            used_times.append(posting_time)
            logging.warning("Profile Seq:%d: Could not find time with 10min interval, using %s", 
                          seq_no, posting_time.strftime("%H:%M"))
        
        schedule.append((profile_id, profile_no, seq_no, posting_time))
        logging.info("Profile Seq:%d scheduled for posting at %s (Kiev time)", 
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
    now = datetime.now(KIEV_TIMEZONE)
    if target_time <= now:
        logging.warning("Target time %s has already passed, posting immediately", target_time.strftime("%H:%M"))
        return
    
    wait_seconds = (target_time - now).total_seconds()
    logging.info("Waiting until %s (Kiev time) - %.1f seconds remaining", 
                target_time.strftime("%H:%M"), wait_seconds)
    
    # Ждем с периодическими проверками (каждые 60 секунд)
    while datetime.now(KIEV_TIMEZONE) < target_time:
        remaining = (target_time - datetime.now(KIEV_TIMEZONE)).total_seconds()
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
        posted_articles_info = []  # Список для финального отчета
        
        for profile_id, profile_no, seq_no, posting_time, article in article_assignments:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            article_topic = article.get('topic', 'N/A')
            is_link = article.get('is_link', 'no') if isinstance(article, dict) else 'no'
            
            # Ждем до времени постинга
            wait_until_time(posting_time)
            
            # Если статья с is_link='yes', заменяем ссылку перед постингом
            if is_link == 'yes':
                logging.info("")
                logging.info("Article has is_link='yes', replacing Bonza link with referral...")
                success = update_article_body_with_replaced_link(
                    pg_conn,
                    selected_table,
                    article_id,
                    seq_no
                )
                if success:
                    logging.info("✓ Link replaced successfully")
                    # Обновляем статью в памяти, чтобы использовать обновленную версию
                    # Получаем обновленную статью из БД
                    try:
                        from poster.db import get_articles_to_post
                        updated_articles = get_articles_to_post(pg_conn, selected_table, [article_id])
                        if updated_articles:
                            article = updated_articles[0]
                            logging.info("Article data refreshed from database")
                    except Exception as e:
                        logging.warning("Failed to refresh article from database: %s", e)
                else:
                    logging.warning("Failed to replace link, continuing with original article")
            
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
                    
                    # Извлекаем ссылку из статьи, если is_link='yes'
                    article_link = ''
                    if is_link == 'yes':
                        body = article.get('body', '') if isinstance(article, dict) else ''
                        if body:
                            # Ищем ссылку bonza.chat в тексте
                            bonza_link_pattern = r'https://bonza\.chat/[^\s<>"]+'
                            matches = re.findall(bonza_link_pattern, body)
                            if matches:
                                article_link = matches[0]  # Берем первую найденную ссылку
                    
                    # Сохраняем информацию для финального отчета
                    posted_articles_info.append({
                        'topic': article_topic,
                        'profile_seq': seq_no,
                        'profile_no': profile_no,
                        'url': url,
                        'has_link': (is_link == 'yes'),
                        'article_link': article_link
                    })
                    
                    # Сокращенное логирование (в режиме SUMMARY)
                    if LOG_MODE.upper() == "SUMMARY":
                        actual_time = datetime.now(KIEV_TIMEZONE)
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
        
        # Отправляем финальный отчет в Telegram
        if posted_articles_info:
            try:
                notify_posting_complete(posted_articles_info)
            except Exception as e:
                logging.warning("Failed to send Telegram posting report: %s", e)
        
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    main()

