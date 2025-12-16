# -*- coding: utf-8 -*-
"""
Скрипт для автоматического постинга статей на Medium через PyAutoGUI и Ads Power.
Читает статьи из PostgreSQL (таблица refined_articles_*) и публикует их на Medium.
"""
import time
import logging
import random
import requests
import pyautogui
import pyperclip
import re
from typing import Optional, List, Dict
from dataclasses import dataclass, field

# Markdown
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logging.warning("Markdown not available. Install with: pip install markdown")

# Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logging.warning("Selenium not available. Install with: pip install selenium")

# PostgreSQL
try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    _pg_v3 = True
except ImportError:
    import psycopg2 as psycopg
    from psycopg2 import sql
    _pg_v3 = False

# Config
from config import POSTGRES_DSN, LOG_LEVEL

# Logs
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
MEDIUM_NEW_STORY_URL = "https://medium.com/new-story"
ADS_POWER_API_URL = "http://local.adspower.net:50325"
ADS_POWER_API_KEY = "856007acdf241361915ed26a00a6d70b"

# Маппинг profile_id -> profile_no для удобства в логах
# Формат: {profile_id: profile_no}
PROFILE_MAPPING = {
    "kqnfhbe": 70,
    "kqnfhbi": 74,
    "kqnfhbo": 80,
    "kqnfhbx": 89,
    "kqnfhby": 90,
    "kqnfhc0": 91,
    "kqnfhc1": 92,
    "kqnfhc2": 93,
    "k107wk78": 125,
    "k107wyp0": 126,
}

# Последовательная нумерация профилей от 1 до 10
# Формат: {profile_no: sequential_no}
PROFILE_SEQUENTIAL_MAPPING = {
    70: 1,
    74: 2,
    80: 3,
    89: 4,
    90: 5,
    91: 6,
    92: 7,
    93: 8,
    125: 9,
    126: 10,
}

# ID профилей Ads Power (циклический перебор) - используем profile_id для API
PROFILE_IDS = list(PROFILE_MAPPING.keys())

# Координаты для кликов (из алгоритма пользователя)
COORDS_TITLE_INPUT = (625, 215)        # Шаг 3: ввод текста (title)
COORDS_PUBLISH_BUTTON_1 = (1301, 118)  # Шаг 7: первая кнопка Publish
COORDS_HASHTAGS_INPUT = (1056, 451)     # Шаг 8: поле ввода хэштегов
COORDS_PUBLISH_BUTTON_2 = (1053, 570)   # Шаг 10: финальная кнопка Publish
COORDS_PUBLISH_BUTTON_2_ALT = (1053, 601) 

# Задержки (базовые значения, будут рандомизированы)
WAIT_AFTER_OPEN_TAB = 15   # Шаг 2: ждём 10 секунд после открытия вкладки
WAIT_AFTER_TITLE_CLICK = 2 # Шаг 3: ждём 1 секунду после клика на поле title
WAIT_AFTER_TITLE_PASTE = 2 # Шаг 4: ждём 1 секунду после вставки title
WAIT_AFTER_ENTER = 2       # Шаг 5: ждём 1 секунду после Enter
WAIT_AFTER_BODY_PASTE = 2  # Шаг 6: ждём 1 секунду после вставки body
WAIT_AFTER_PUBLISH_1 = 5   # Шаг 7: ждём 3 секунды после первой кнопки Publish
WAIT_AFTER_HASHTAGS_CLICK = 2  # Шаг 8: ждём 1 секунду после клика на поле хэштегов
WAIT_BETWEEN_HASHTAGS = 2      # Шаг 9: ждём 1 секунду между хэштегами
WAIT_AFTER_PUBLISH_2 = 25      # Шаг 10: ждём 15 секунд после финальной кнопки Publish
WAIT_AFTER_COPY = 2            # Шаг 12: ждём 1 секунду после Ctrl+C

# Настройка PyAutoGUI
pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True

# Глобальный словарь профилей
@dataclass
class Profile:
    """Структура для хранения информации о профиле Ads Power"""
    profile_no: int
    profile_id: str
    driver: Optional[object] = None  # Selenium WebDriver
    window_tag: str = field(init=False)
    medium_window_handle: Optional[str] = None  # Handle вкладки с Medium
    sequential_no: int = field(init=False)      # Последовательный номер (1-10)
    tag_window_handle: Optional[str] = None     # Handle вкладки-ярлыка (about:blank с window_tag)

    def __post_init__(self):
        self.window_tag = f"ADS_PROFILE_{self.profile_no}"
        self.sequential_no = get_sequential_no(self.profile_no) or 0

# Глобальный словарь профилей: {profile_no: Profile}
profiles: Dict[int, Profile] = {}


def random_delay(base_seconds: float, variance_percent: float = 10.0) -> float:
    variance = base_seconds * (variance_percent / 100.0)
    min_delay = base_seconds - variance
    max_delay = base_seconds + variance
    delay = random.uniform(min_delay, max_delay)
    return delay


def wait_with_log(seconds: float, step_name: str, variance_percent: float = 10.0):
    actual_delay = random_delay(seconds, variance_percent)
    logging.debug(
        "  [%s] Waiting %.2f seconds (base: %.1f ±%.0f%%)",
        step_name, actual_delay, seconds, variance_percent
    )
    time.sleep(actual_delay)


def get_pg_conn():
    logging.debug("Connecting to PostgreSQL...")
    try:
        if _pg_v3:
            conn = psycopg.connect(POSTGRES_DSN, row_factory=dict_row)
        else:
            conn = psycopg.connect(POSTGRES_DSN)
            from psycopg2.extras import RealDictCursor
            conn.cursor_factory = RealDictCursor
        logging.info("✓ Connected to PostgreSQL")
        return conn
    except Exception as e:
        logging.error("Failed to connect to PostgreSQL: %s", e)
        raise


def get_refined_articles_tables(pg_conn) -> List[str]:
    logging.debug("Fetching refined_articles tables...")
    query = sql.SQL("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE 'refined_articles_%'
        ORDER BY table_name
    """)

    try:
        with pg_conn.cursor() as cur:
            cur.execute(query)
            tables = [row['table_name'] if isinstance(row, dict) else row[0] for row in cur.fetchall()]
        logging.info("Found %d refined_articles table(s): %s", len(tables), tables)
        return tables
    except Exception as e:
        logging.error("Error fetching tables: %s", e)
        raise


def ensure_profile_id_column(pg_conn, table_name: str) -> None:
    logging.debug("Checking for profile_id column in table %s...", table_name)
    check_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'profile_id'
    """)

    with pg_conn.cursor() as cur:
        cur.execute(check_query, (table_name,))
        has_column = cur.fetchone() is not None

    if not has_column:
        logging.info("Adding profile_id column to table %s...", table_name)
        alter_query = sql.SQL("""
            ALTER TABLE {table}
            ADD COLUMN profile_id INTEGER
        """).format(table=sql.Identifier(table_name))

        try:
            with pg_conn.cursor() as cur:
                cur.execute(alter_query)
            pg_conn.commit()
            logging.info("✓ Added profile_id column to table %s", table_name)
        except Exception as e:
            logging.error("Error adding profile_id column: %s", e)
            pg_conn.rollback()
            raise
    else:
        logging.debug("Column profile_id already exists in table %s", table_name)


def parse_id_selection(s: str) -> List[int]:
    ids = []
    parts = s.replace(' ', '').split(',')

    for part in parts:
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                ids.extend(range(start, end + 1))
            except ValueError:
                logging.warning("Invalid range format: %s", part)
        else:
            try:
                ids.append(int(part))
            except ValueError:
                logging.warning("Invalid ID format: %s", part)

    return sorted(list(dict.fromkeys(ids)))


def get_articles_to_post(pg_conn, table_name: str, article_ids: Optional[List[int]] = None) -> List[dict]:
    logging.debug("Getting articles from table: %s", table_name)

    # Безопасно проверяем наличие колонки hashtag5
    logging.debug("Checking for hashtag5 column...")
    has_hashtag5 = False
    try:
        check_col_query = sql.SQL("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = %s 
            AND column_name = 'hashtag5'
        """)

        with pg_conn.cursor() as cur:
            cur.execute(check_col_query, (table_name,))
            has_hashtag5 = cur.fetchone() is not None
        logging.info("Table has hashtag5 column: %s", has_hashtag5)
    except Exception as e:
        # Если проверка не удалась, предполагаем что колонки нет
        logging.warning("Could not check for hashtag5 column (assuming it doesn't exist): %s", e)
        has_hashtag5 = False

    # Формируем список колонок в зависимости от наличия hashtag5
    if has_hashtag5:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, hashtag5, url, profile_id"
    else:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, url, profile_id"

    if article_ids:
        logging.info("Fetching articles by IDs: %s", article_ids)
        query = sql.SQL("""
            SELECT {cols}
            FROM {table}
            WHERE id = ANY(%s)
            ORDER BY id ASC
        """).format(
            cols=sql.SQL(select_cols),
            table=sql.Identifier(table_name)
        )
        params = (article_ids,)
    else:
        logging.info("Fetching all unpublished articles (url IS NULL or empty)")
        query = sql.SQL("""
            SELECT {cols}
            FROM {table}
            WHERE url IS NULL OR url = ''
            ORDER BY id ASC
        """).format(
            cols=sql.SQL(select_cols),
            table=sql.Identifier(table_name)
        )
        params = ()

    try:
        with pg_conn.cursor() as cur:
            # Логируем запрос для отладки
            try:
                query_str = query.as_string(pg_conn) if hasattr(query, 'as_string') else str(query)
                logging.debug("Executing query: %s with params: %s", query_str, params)
            except Exception:
                logging.debug("Executing query with params: %s", params)

            cur.execute(query, params)
            articles = cur.fetchall()
            logging.info("Fetched %d article(s) from database", len(articles))

            if articles:
                logging.debug("Article IDs: %s", [a['id'] if isinstance(a, dict) else a[0] for a in articles[:10]])
            elif article_ids:
                logging.warning("No articles found for IDs: %s. They may not exist in table %s", article_ids, table_name)

            return articles
    except Exception as e:
        logging.error("Error fetching articles: %s", e, exc_info=True)
        try:
            query_str = query.as_string(pg_conn) if hasattr(query, 'as_string') else str(query)
            logging.error("Failed query: %s", query_str)
            logging.error("Query params: %s", params)
        except Exception:
            logging.error("Could not format query string")
        raise


def update_article_url_and_profile(pg_conn, table_name: str, article_id: int, url: str, profile_id: int) -> None:
    logging.debug("Updating URL and profile_id for article ID %s in table %s", article_id, table_name)
    query = sql.SQL("""
        UPDATE {table}
        SET url = %s, profile_id = %s
        WHERE id = %s
    """).format(table=sql.Identifier(table_name))

    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, (url, profile_id, article_id))
            rows_affected = cur.rowcount
        pg_conn.commit()
        if rows_affected > 0:
            logging.info("✓ Updated URL and profile_id for article ID %s: url=%s, profile_id=%s", article_id, url, profile_id)
        else:
            logging.warning("No rows updated for article ID %s (article may not exist)", article_id)
    except Exception as e:
        logging.error("Error updating URL and profile_id for article ID %s: %s", article_id, e)
        raise


def get_profile_no(profile_id: str) -> int:
    return PROFILE_MAPPING.get(profile_id, 0)


def get_profile_id(profile_no: int) -> Optional[str]:
    for pid, pno in PROFILE_MAPPING.items():
        if pno == profile_no:
            return pid
    return None


def get_sequential_no(profile_no: int) -> Optional[int]:
    return PROFILE_SEQUENTIAL_MAPPING.get(profile_no)


def get_profile_id_by_sequential_no(sequential_no: int) -> Optional[str]:
    for profile_no, seq_no in PROFILE_SEQUENTIAL_MAPPING.items():
        if seq_no == sequential_no:
            profile_id = get_profile_id(profile_no)
            if profile_id:
                return profile_id
    return None


def get_profile_no_by_sequential_no(sequential_no: int) -> Optional[int]:
    for profile_no, seq_no in PROFILE_SEQUENTIAL_MAPPING.items():
        if seq_no == sequential_no:
            return profile_no
    return None


def markdown_to_html(markdown_text: str) -> str:
    if not MARKDOWN_AVAILABLE:
        logging.warning("Markdown library not available, returning plain text wrapped in <p> tags")
        paragraphs = markdown_text.split('\n\n')
        html_parts = []
        for para in paragraphs:
            para = para.strip()
            if para:
                html_parts.append(f"<p>{para}</p>")
        return '\n'.join(html_parts)

    try:
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        html = md.convert(markdown_text)

        html = re.sub(r'^<html[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'</html>$', '', html, flags=re.IGNORECASE)
        html = re.sub(r'^<body[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'</body>$', '', html, flags=re.IGNORECASE)
        html = html.strip()

        logging.debug("Markdown converted to HTML (length: %d chars)", len(html))
        return html
    except Exception as e:
        logging.error("Error converting Markdown to HTML: %s", e)
        paragraphs = markdown_text.split('\n\n')
        html_parts = []
        for para in paragraphs:
            para = para.strip()
            if para:
                html_parts.append(f"<p>{para}</p>")
        return '\n'.join(html_parts)


def html_to_plain_text(html: str) -> str:
    text = re.sub(r'<[^>]+>', '', html)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


class HtmlClipboard:
    CF_HTML = None

    MARKER_BLOCK_OUTPUT = (
        "Version:1.0\r\n"
        "StartHTML:%09d\r\n"
        "EndHTML:%09d\r\n"
        "StartFragment:%09d\r\n"
        "EndFragment:%09d\r\n"
        "StartSelection:%09d\r\n"
        "EndSelection:%09d\r\n"
        "SourceURL:%s\r\n"
    )

    DEFAULT_HTML_BODY = (
        "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0 Transitional//EN\">"
        "<HTML><HEAD></HEAD><BODY><!--StartFragment-->%s<!--EndFragment--></BODY></HTML>"
    )

    @classmethod
    def get_cf_html(cls):
        import win32clipboard
        if cls.CF_HTML is None:
            cls.CF_HTML = win32clipboard.RegisterClipboardFormat("HTML Format")
        return cls.CF_HTML

    @classmethod
    def put_fragment(cls, fragment: str, source: str = "about:blank") -> None:
        import win32clipboard

        html = cls.DEFAULT_HTML_BODY % fragment
        fragment_start = html.index(fragment)
        fragment_end = fragment_start + len(fragment)

        selection_start = fragment_start
        selection_end = fragment_end

        dummy_prefix = cls.MARKER_BLOCK_OUTPUT % (0, 0, 0, 0, 0, 0, source)
        len_prefix = len(dummy_prefix)

        prefix = cls.MARKER_BLOCK_OUTPUT % (
            len_prefix,
            len(html) + len_prefix,
            fragment_start + len_prefix,
            fragment_end + len_prefix,
            selection_start + len_prefix,
            selection_end + len_prefix,
            source,
        )

        src = (prefix + html).encode("UTF-8")

        win32clipboard.OpenClipboard(0)
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(cls.get_cf_html(), src)
        finally:
            win32clipboard.CloseClipboard()


def copy_markdown_as_rich_text(markdown_text: str) -> bool:
    try:
        html_fragment = markdown_to_html(markdown_text)
        HtmlClipboard.put_fragment(html_fragment)
        logging.info("✓ Markdown copied to clipboard as CF_HTML (HTML Format)")
        logging.debug("  HTML fragment preview: %s", html_fragment[:200])
        return True
    except ImportError:
        logging.warning("pywin32 (win32clipboard) not available, fallback to plain text")
        pyperclip.copy(markdown_text)
        return False
    except Exception as e:
        logging.error("Error in copy_markdown_as_rich_text: %s", e, exc_info=True)
        pyperclip.copy(markdown_text)
        return False


# ==========================
# Дальше — AdsPower / Selenium / постинг
# ==========================

def check_ads_power_profile_status(profile_id: str) -> Optional[dict]:
    profile_no = get_profile_no(profile_id)
    logging.debug("Checking status of Ads Power profile ID: %s (No: %s)", profile_id, profile_no)

    endpoint = f"{ADS_POWER_API_URL}/api/v2/browser-profile/active"
    params = {"profile_id": profile_id}
    headers = {}
    if ADS_POWER_API_KEY:
        headers["Authorization"] = f"Bearer {ADS_POWER_API_KEY}"

    try:
        response = requests.get(endpoint, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.debug("  HTTP error: %s", response.status_code)
            return None

        data = response.json()
        if data.get("code") != 0:
            logging.debug("  API returned error: %s", data.get("msg", "Unknown error"))
            return None

        profile_data = data.get("data", {}) or {}
        status = profile_data.get("status", "Unknown")
        logging.info("Profile ID %s (No: %s) status: %s", profile_id, profile_no, status)
        return profile_data

    except requests.exceptions.RequestException as e:
        logging.error("✗ Request error checking profile status: %s", e)
        return None
    except Exception as e:
        logging.error("✗ Unexpected error checking profile status: %s", e)
        return None


def _adspower_start_profile(profile_id: str) -> bool:
    endpoint = f"{ADS_POWER_API_URL}/api/v2/browser-profile/start"
    headers = {"Content-Type": "application/json"}
    if ADS_POWER_API_KEY:
        headers["Authorization"] = f"Bearer {ADS_POWER_API_KEY}"

    try:
        resp = requests.post(endpoint, json={"profile_id": profile_id}, headers=headers, timeout=30)
        if resp.status_code != 200:
            logging.error("Failed to start profile: HTTP %d", resp.status_code)
            return False
        data = resp.json()
        if data.get("code") != 0:
            logging.error("Failed to start profile: %s", data.get("msg", "Unknown error"))
            return False
        return True
    except Exception as e:
        logging.error("Error starting profile: %s", e)
        return False


def _wait_profile_active(profile_id: str, timeout_s: int = 90, poll_s: float = 3.0) -> Optional[dict]:
    """
    Ждёт, пока профиль станет Active и появятся ws.selenium + webdriver.
    Возвращает profile_status dict (data из /active) или None.
    """
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        st = check_ads_power_profile_status(profile_id)
        if st:
            last_status = st
            status = st.get("status")
            ws = st.get("ws") or {}
            selenium_addr = ws.get("selenium")
            webdriver_path = st.get("webdriver")
            if status == "Active" and selenium_addr and webdriver_path:
                return st
        time.sleep(poll_s)
    if last_status:
        logging.error("Profile %s did not become ready in time. Last status=%s", profile_id, last_status.get("status"))
    else:
        logging.error("Profile %s did not become ready in time (no status).", profile_id)
    return None



def _safe_switch_to(driver, handle: str) -> bool:
    """Безопасно переключается на window handle (вкладку)."""
    try:
        driver.switch_to.window(handle)
        return True
    except Exception:
        return False


def _ensure_tag_tab(profile: 'Profile') -> bool:
    """
    Гарантирует наличие отдельной вкладки-ярлыка (about:blank) с document.title == profile.window_tag.

    Зачем:
    - pygetwindow ищет окно по заголовку активной вкладки. Medium часто меняет title, поэтому держим стабильный tag.
    - Для фокуса окна можно временно активировать tag-вкладку, сфокусировать окно, и вернуть Medium.
    """
    if not getattr(profile, "driver", None):
        return False

    driver = profile.driver
    try:
        handles = driver.window_handles or []

        # Если tag handle уже известен и жив
        if profile.tag_window_handle and profile.tag_window_handle in handles:
            _safe_switch_to(driver, profile.tag_window_handle)
            try:
                driver.get("about:blank")
            except Exception:
                pass
            try:
                driver.execute_script("document.title = arguments[0];", profile.window_tag)
            except Exception:
                pass
            return True

        # Создаём НОВУЮ вкладку (не ломаем существующие вкладки профиля)
        created = False
        try:
            # Selenium 4+
            driver.switch_to.new_window("tab")
            created = True
        except Exception:
            try:
                driver.execute_script("window.open('about:blank','_blank');")
                created = True
            except Exception:
                created = False

        if not created:
            return False

        time.sleep(0.2)
        handles = driver.window_handles or []
        if handles:
            _safe_switch_to(driver, handles[-1])

        try:
            driver.get("about:blank")
        except Exception:
            pass
        try:
            driver.execute_script("document.title = arguments[0];", profile.window_tag)
        except Exception:
            pass

        profile.tag_window_handle = driver.current_window_handle
        return True

    except Exception:
        return False


def _find_existing_medium_tab(profile: 'Profile') -> Optional[str]:
    """Ищет уже открытую вкладку Medium в этом профиле (по URL)."""
    if not getattr(profile, "driver", None):
        return None
    driver = profile.driver
    try:
        for h in driver.window_handles or []:
            try:
                driver.switch_to.window(h)
                url = (driver.current_url or "").lower()
                if "medium.com" in url:
                    return h
            except Exception:
                continue
    except Exception:
        return None
    return None

def close_profile(profile_id: str) -> bool:
    profile_no = get_profile_no(profile_id)
    logging.info("Closing profile ID: %s (No: %s)", profile_id, profile_no)

    endpoint = f"{ADS_POWER_API_URL}/api/v2/browser-profile/stop"
    headers = {"Content-Type": "application/json"}
    if ADS_POWER_API_KEY:
        headers["Authorization"] = f"Bearer {ADS_POWER_API_KEY}"

    payload = {"profile_id": profile_id}

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            logging.error("Failed to close profile %d: HTTP %d", profile_no, response.status_code)
            return False

        data = response.json()
        if data.get("code") != 0:
            logging.error("Failed to close profile %d: %s", profile_no, data.get("msg", "Unknown error"))
            return False

        logging.info("✓ Profile %d (ID: %s) closed successfully", profile_no, profile_id)

        if profile_no in profiles:
            profile = profiles[profile_no]
            if profile.driver:
                try:
                    profile.driver.quit()
                except Exception as e:
                    logging.debug("Error quitting driver for profile %d: %s", profile_no, e)
                profile.driver = None
            profile.medium_window_handle = None
            profile.tag_window_handle = None

        return True
    except Exception as e:
        logging.error("Error closing profile %d: %s", profile_no, e)
        return False


def ensure_profile_ready(profile_no: int) -> bool:
    """
    ЕДИНАЯ точка подготовки профиля:
    - если профиль закрыт/не Active: стартуем через API и ждём Active + ws.selenium + webdriver
    - подключаем Selenium к уже запущенному профилю
    - создаём/поддерживаем вкладку-ярлык (tag tab) для стабильного фокуса окна
    """
    if not SELENIUM_AVAILABLE:
        logging.error("Selenium not available! Install with: pip install selenium")
        return False

    if profile_no not in profiles:
        profile_id = get_profile_id(profile_no)
        if not profile_id:
            logging.error("Profile No %d not found in PROFILE_MAPPING", profile_no)
            return False
        profiles[profile_no] = Profile(profile_no=profile_no, profile_id=profile_id)

    profile = profiles[profile_no]

    # Если driver уже жив — просто проверим/восстановим tag tab
    if profile.driver:
        try:
            _ = profile.driver.current_url
            _ensure_tag_tab(profile)
            return True
        except Exception:
            profile.driver = None
            profile.tag_window_handle = None

    # 1) Гарантируем Active + наличие ws.selenium/webdriver
    profile_status = check_ads_power_profile_status(profile.profile_id)
    ws = (profile_status or {}).get("ws") or {}
    status = (profile_status or {}).get("status")
    selenium_ok = bool(ws.get("selenium"))
    webdriver_ok = bool((profile_status or {}).get("webdriver"))

    if status != "Active" or not selenium_ok or not webdriver_ok:
        logging.info("Profile %d (ID: %s) is not ready/Active, starting via API...", profile_no, profile.profile_id)
        if not _adspower_start_profile(profile.profile_id):
            return False
        profile_status = _wait_profile_active(profile.profile_id, timeout_s=120, poll_s=3.0)
        if not profile_status:
            return False

    # Иногда Active есть, но ws/webdriver приезжают позже
    ws = (profile_status or {}).get("ws") or {}
    selenium_address = ws.get("selenium") or ""
    webdriver_path = (profile_status or {}).get("webdriver") or ""
    if not selenium_address or not webdriver_path:
        profile_status = _wait_profile_active(profile.profile_id, timeout_s=60, poll_s=2.0)
        if not profile_status:
            return False
        ws = (profile_status or {}).get("ws") or {}
        selenium_address = ws.get("selenium") or ""
        webdriver_path = (profile_status or {}).get("webdriver") or ""

    if not selenium_address or not webdriver_path:
        logging.error("Missing selenium address or webdriver path for profile %d", profile_no)
        return False

    # 2) Подключаем Selenium к профилю
    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", selenium_address)

        service = Service(webdriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Может фейлиться/не иметь эффекта — реальную максимизацию делаем через pygetwindow.
        try:
            driver.maximize_window()
        except Exception:
            pass

        profile.driver = driver

        # 3) Создаём tag-tab для стабильного поиска/фокуса окна
        _ensure_tag_tab(profile)

        logging.info(
            "✓ Profile %d (ID: %s) ready with window_tag: %s",
            profile_no, profile.profile_id, profile.window_tag
        )
        return True

    except Exception as e:
        logging.error("Error creating Selenium driver for profile %d: %s", profile_no, e)
        return False



def focus_profile_window(profile_no: int) -> bool:
    """
    Безопасно фокусирует и максимизирует окно профиля.
    Требования:
    - если профиль открыт: просто вывести на передний план + максимизировать
    - если уже максимизировано: ошибок быть не должно (любые ошибки maximize игнорируем)
    - если окно не находится из-за title Medium: временно активируем tag-tab и повторяем поиск
    """
    if profile_no not in profiles:
        logging.error("Profile %d not found in profiles dict", profile_no)
        return False

    profile = profiles[profile_no]

    try:
        import pygetwindow as gw

        def _find():
            wins = gw.getWindowsWithTitle(profile.window_tag)
            if wins:
                return wins
            for w in gw.getAllWindows():
                if profile.window_tag in (w.title or ""):
                    return [w]
            return []

        windows = _find()

        # Если не нашли — попробуем активировать tag tab и поискать ещё раз
        if not windows and profile.driver:
            try:
                _ensure_tag_tab(profile)
                if profile.tag_window_handle:
                    _safe_switch_to(profile.driver, profile.tag_window_handle)
                    time.sleep(0.2)  # дать ОС обновить заголовок
                windows = _find()
            except Exception:
                windows = _find()

        if not windows:
            logging.warning("Window with tag '%s' not found for profile %d", profile.window_tag, profile_no)
            return False

        win = windows[0]

        try:
            if getattr(win, "isMinimized", False):
                win.restore()
                time.sleep(0.15)
        except Exception:
            pass

        try:
            win.activate()
            time.sleep(0.15)
        except Exception:
            pass

        try:
            win.maximize()
            time.sleep(0.2)
        except Exception:
            # уже максимизировано или maximize не поддержан — не критично
            pass

        logging.info("✓ Profile %d window focused and maximized: %s", profile_no, win.title)
        return True

    except ImportError:
        logging.error("pygetwindow not available")
        return False
    except Exception as e:
        logging.error("Error focusing window for profile %d: %s", profile_no, e)
        return False



def _wait_document_ready(driver, timeout_s: int = 30) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            state = driver.execute_script("return document.readyState")
            if state == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def ensure_medium_tab_open(profile: Profile, profile_no: int) -> bool:
    """
    Убеждается, что:
    1) вкладка Medium существует (или создаётся),
    2) она открыта на MEDIUM_NEW_STORY_URL,
    3) В КОНЦЕ именно эта вкладка активна на экране (чтобы PyAutoGUI работал стабильно).

    Ключевой момент: для надёжного фокуса окна используем tag-tab (стабильный title),
    потом возвращаемся на Medium-tab.
    """
    if not profile.driver:
        logging.error("Driver not available for profile %d", profile_no)
        return False

    driver = profile.driver

    try:
        # 0) Гарантируем tag tab
        _ensure_tag_tab(profile)

        handles = driver.window_handles or []

        # 1) Если уже есть сохранённый medium_window_handle — пробуем его
        if profile.medium_window_handle and profile.medium_window_handle in handles:
            if not _safe_switch_to(driver, profile.medium_window_handle):
                profile.medium_window_handle = None

        # 2) Если нет — ищем существующую вкладку medium.com
        if not profile.medium_window_handle:
            found = _find_existing_medium_tab(profile)
            if found:
                profile.medium_window_handle = found
                _safe_switch_to(driver, found)

        # 3) Если всё ещё нет — открываем новую вкладку
        if not profile.medium_window_handle:
            try:
                driver.switch_to.new_window("tab")
            except Exception:
                driver.execute_script("window.open('about:blank','_blank');")
                time.sleep(0.2)
                handles = driver.window_handles or []
                if handles:
                    _safe_switch_to(driver, handles[-1])
            profile.medium_window_handle = driver.current_window_handle

        # 4) Навигация на new-story
        try:
            driver.get(MEDIUM_NEW_STORY_URL)
        except Exception as e:
            logging.debug("driver.get(MEDIUM_NEW_STORY_URL) failed (continuing): %s", e)

        _wait_document_ready(driver, timeout_s=30)
        time.sleep(0.3)

        # (необязательно) Добавим tag в title medium вкладки — иногда помогает, но не полагаемся на это.
        try:
            driver.execute_script(
                "document.title = arguments[0] + ' | ' + (document.title || 'Medium');",
                profile.window_tag
            )
        except Exception:
            pass

        # 5) Фокусируем окно через tag-tab
        if profile.tag_window_handle:
            _safe_switch_to(driver, profile.tag_window_handle)
            try:
                driver.execute_script("document.title = arguments[0];", profile.window_tag)
            except Exception:
                pass
            time.sleep(0.2)

        focus_profile_window(profile_no)
        time.sleep(0.25)

        # 6) Возвращаем активной вкладкой Medium (это важно для PyAutoGUI)
        if profile.medium_window_handle:
            _safe_switch_to(driver, profile.medium_window_handle)
            try:
                driver.execute_script("window.focus();")
            except Exception:
                pass
            time.sleep(0.25)

        profile.medium_window_handle = driver.current_window_handle
        logging.info("✓ Medium tab ready & active. Handle=%s URL=%s", profile.medium_window_handle, driver.current_url)

        logging.info("Waiting %.0f seconds for page to stabilize before starting PyAutoGUI cycle...", WAIT_AFTER_OPEN_TAB)
        wait_with_log(WAIT_AFTER_OPEN_TAB, "Page load wait", 10.0)
        return True

    except Exception as e:
        logging.error("Failed to open Medium URL: %s", e, exc_info=True)
        return False



def find_window_by_tag(profile: Profile) -> Optional[str]:
    """
    Находит window handle вкладки, где title содержит window_tag.
    С учётом того, что у нас есть отдельная tag-tab, это почти всегда работает.
    """
    if not profile.driver:
        return None

    try:
        handles = profile.driver.window_handles or []
        if not handles:
            return None

        # 1) Сначала tag-tab, если есть
        if profile.tag_window_handle and profile.tag_window_handle in handles:
            return profile.tag_window_handle

        # 2) Ищем по title
        for h in handles:
            try:
                profile.driver.switch_to.window(h)
                title = profile.driver.title or ""
                if profile.window_tag in title:
                    return h
            except Exception:
                continue

        # 3) Иначе Medium handle
        if profile.medium_window_handle and profile.medium_window_handle in handles:
            return profile.medium_window_handle

        return handles[0]
    except Exception as e:
        logging.error("Error finding window by tag: %s", e)
        return None


def minimize_profile_window(profile_no: int) -> bool:
    if profile_no not in profiles:
        return False

    profile = profiles[profile_no]

    try:
        import pygetwindow as gw

        windows = gw.getWindowsWithTitle(profile.window_tag)
        if not windows:
            for win in gw.getAllWindows():
                if profile.window_tag in (win.title or ""):
                    windows = [win]
                    break

        if windows:
            windows[0].minimize()
            logging.debug("Profile %d window minimized", profile_no)
            return True

        return False
    except ImportError:
        logging.error("pygetwindow not available for minimizing window")
        return False
    except Exception as e:
        logging.debug("Error minimizing window for profile %d: %s", profile_no, e)
        return False


def open_and_maximize_profile(sequential_no: int) -> Optional[str]:
    """
    Открывает и подготавливает профиль по sequential_no (1-10) так, как нужно для PyAutoGUI:

    - если профиль закрыт: стартует через API и ждёт готовности (делает ensure_profile_ready)
    - если профиль уже открыт: НЕ перезапускает, а просто цепляет Selenium и фокусирует/максимизирует окно
    - затем гарантирует Medium new-story вкладку и делает её активной на экране
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

    if not ensure_profile_ready(profile_no):
        logging.error("Failed to ensure profile %d is ready", profile_no)
        return None

    # Фокус/максимизация окна (безопасно и без ошибок)
    if not focus_profile_window(profile_no):
        logging.warning("Failed to focus/maximize window, but continuing...")

    # Medium вкладка должна быть активна на экране
    profile = profiles[profile_no]
    if not ensure_medium_tab_open(profile, profile_no):
        logging.error("Failed to open Medium tab for profile %d", profile_no)
        return None

    logging.info("=" * 60)
    logging.info("✓ Profile ready: window focused, Medium tab active")
    logging.info("=" * 60)
    return profile_id



def open_ads_power_profile(profile_id: str) -> Optional[str]:
    profile_no = get_profile_no(profile_id)
    if profile_no == 0:
        logging.error("Profile ID %s not found in PROFILE_MAPPING", profile_id)
        return None

    sequential_no = get_sequential_no(profile_no)
    if not sequential_no:
        logging.error("Profile No %d has no sequential_no mapping", profile_no)
        return None

    return open_and_maximize_profile(sequential_no)


def post_article_to_medium(article: dict, profile_id: str) -> Optional[str]:
    # --- НЕ ТРОГАЛ: всё как у тебя ниже ---
    article_id = article.get('id') if isinstance(article, dict) else article[0]
    profile_no = get_profile_no(profile_id)
    sequential_no = get_sequential_no(profile_no)
    profile_info = f"{profile_id} (No: {profile_no}" + (f", Seq: {sequential_no})" if sequential_no else ")")
    logging.info("="*60)
    logging.info("Posting article ID %s using profile: %s", article_id, profile_info)
    logging.info("="*60)

    try:
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

        logging.info("="*60)
        logging.info("STEP 1: Ensuring profile window is active and on Medium tab...")
        try:
            profile_no = get_profile_no(profile_id)
            focus_profile_window(profile_no)
            time.sleep(1)

            profile = profiles[profile_no]
            if profile.driver and profile.medium_window_handle:
                try:
                    profile.driver.switch_to.window(profile.medium_window_handle)
                    current_url = profile.driver.current_url
                    logging.info("  Current URL on Medium tab: %s", current_url)

                    if 'medium.com' not in current_url:
                        logging.warning("  Not on Medium page, navigating to Medium...")
                        profile.driver.get(MEDIUM_NEW_STORY_URL)
                        time.sleep(2)
                        profile.medium_window_handle = profile.driver.current_window_handle
                except Exception as e:
                    logging.warning("  Failed to switch to Medium tab: %s, trying to navigate...", e)
                    if profile.driver:
                        profile.driver.get(MEDIUM_NEW_STORY_URL)
                        time.sleep(2)
                        profile.medium_window_handle = profile.driver.current_window_handle

            logging.info("  ✓ Profile window is active (Medium URL already opened via Selenium)")
        except Exception as e:
            logging.error("  ✗ Failed to ensure window is active: %s", e)
            return None

        logging.info("STEP 1.1: Reloading the page")
        try:
            time.sleep(2)
            pyautogui.press('f5')
            logging.info("Reloaded")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None

        logging.info("STEP 2: Clicking on title input field...")
        logging.info("  Coordinates: %s", COORDS_TITLE_INPUT)
        try:
            pyautogui.click(*COORDS_TITLE_INPUT)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None

        wait_with_log(WAIT_AFTER_TITLE_CLICK, "STEP 2", 10.0)

        logging.info("STEP 3: Pasting title...")
        logging.info("  Title length: %d characters", len(title))
        try:
            pyperclip.copy(title)
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')
            logging.info("  ✓ Title pasted successfully")
        except Exception as e:
            logging.error("  ✗ Failed to paste title: %s", e)
            return None

        wait_with_log(WAIT_AFTER_TITLE_PASTE, "STEP 3", 10.0)

        logging.info("STEP 4: Pressing Enter...")
        try:
            pyautogui.press('enter')
            logging.info("  ✓ Enter pressed successfully")
        except Exception as e:
            logging.error("  ✗ Failed to press Enter: %s", e)
            return None

        wait_with_log(WAIT_AFTER_ENTER, "STEP 4", 10.0)

        logging.info("STEP 5: Pasting body as Rich Text (HTML via CF_HTML)...")
        logging.info("  Body length: %d characters", len(body))

        time.sleep(1.5)

        try:
            logging.debug("  Converting Markdown to HTML and placing to clipboard as CF_HTML...")
            if not copy_markdown_as_rich_text(body):
                logging.warning("  Failed to copy as Rich Text, falling back to plain text")
                pyperclip.copy(body)

            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            logging.info("  ✓ Body pasted (via Ctrl+V)")
        except Exception as e:
            logging.error("  ✗ Failed to paste body: %s", e, exc_info=True)
            return None

        wait_with_log(WAIT_AFTER_BODY_PASTE, "STEP 5", 10.0)

        logging.info("STEP 6: Clicking first Publish button...")
        logging.info("  Coordinates: %s", COORDS_PUBLISH_BUTTON_1)
        logging.info("  Waiting 5 seconds before clicking Publish...")
        time.sleep(5)
        try:
            pyautogui.click(*COORDS_PUBLISH_BUTTON_1)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None

        wait_with_log(WAIT_AFTER_PUBLISH_1, "STEP 6", 10.0)

        logging.info("STEP 7: Clicking on hashtags input field...")
        logging.info("  Coordinates: %s", COORDS_HASHTAGS_INPUT)
        try:
            pyautogui.click(*COORDS_HASHTAGS_INPUT)
            time.sleep(1)
            pyautogui.click(*COORDS_HASHTAGS_INPUT)
            logging.info("  ✓ Clicked successfully")

        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None

        wait_with_log(WAIT_AFTER_HASHTAGS_CLICK, "STEP 7", 10.0)

        logging.info("STEP 8: Pasting hashtags one by one...")
        logging.info("  Hashtags to paste: %s", hashtags[:5])
        try:
            for i, hashtag in enumerate(hashtags[:5]):
                if hashtag:
                    logging.debug("  Pasting hashtag %d/%d: %s", i+1, len(hashtags[:5]), hashtag)
                    pyperclip.copy(hashtag)
                    time.sleep(0.2)
                    pyautogui.hotkey('ctrl', 'v')
                    wait_with_log(WAIT_BETWEEN_HASHTAGS, f"STEP 8 hashtag {i+1}", 10.0)

                    if i < len(hashtags[:5]) - 1:
                        logging.debug("  Adding comma after hashtag %d", i+1)
                        pyautogui.write(',', interval=0.1)
                        wait_with_log(WAIT_BETWEEN_HASHTAGS, f"STEP 8 comma {i+1}", 10.0)

            logging.info("  ✓ All hashtags pasted successfully")
            logging.info("  Final hashtags: %s", ", ".join(hashtags[:5]))
        except Exception as e:
            logging.error("  ✗ Failed to paste hashtags: %s", e)
            return None

        logging.info("STEP 9: Clicking final Publish button...")
        logging.info("  Coordinates: %s", COORDS_PUBLISH_BUTTON_2)
        logging.info("  Waiting 3 seconds before clicking final Publish...")
        time.sleep(3)
        try:
            pyautogui.click(*COORDS_PUBLISH_BUTTON_2)
            logging.info("  ✓ First click successful")
            time.sleep(1)
            pyautogui.click(*COORDS_PUBLISH_BUTTON_2_ALT)
            logging.info("  ✓ Second click successful")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None

        wait_with_log(WAIT_AFTER_PUBLISH_2, "STEP 9", 10.0)
        logging.info("  ✓ Publication should be complete")

        logging.info("STEP 10: Getting published article URL via Selenium...")
        try:
            profile_no = get_profile_no(profile_id)
            profile = profiles[profile_no]

            if profile.driver and profile.medium_window_handle:
                try:
                    profile.driver.switch_to.window(profile.medium_window_handle)
                except (Exception, AttributeError) as e:
                    logging.debug("Window handle invalid, searching for Medium window: %s", e)
                    all_windows = profile.driver.window_handles
                    for window in all_windows:
                        try:
                            profile.driver.switch_to.window(window)
                            current_url = profile.driver.current_url
                            if 'medium.com' in current_url and '/@' in current_url:
                                profile.medium_window_handle = window
                                break
                        except (Exception, AttributeError):
                            continue
                    else:
                        if all_windows:
                            profile.driver.switch_to.window(all_windows[-1])

            if profile.driver:
                url = profile.driver.current_url
                logging.info("  ✓ URL retrieved via Selenium")
                logging.info("  Retrieved URL: %s", url)
            else:
                logging.warning("  Driver not available, using PyAutoGUI fallback...")
                pyautogui.hotkey('ctrl', 'l')
                time.sleep(0.5)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(1)
                url = pyperclip.paste()
                logging.info("  ✓ URL copied from clipboard (fallback)")
                logging.info("  Retrieved URL: %s", url)
        except Exception as e:
            logging.error("  ✗ Failed to get URL: %s", e)
            return None

        if url and url.startswith('http'):
            logging.info("="*60)
            logging.info("✓ Article published successfully!")
            logging.info("URL: %s", url)
            logging.info("="*60)
            return url
        else:
            logging.warning("="*60)
            logging.warning("⚠ URL not retrieved or invalid")
            logging.warning("  Clipboard content: %s", url)
            logging.warning("  Expected: URL starting with 'http'")
            logging.warning("="*60)
            return None

    except Exception as e:
        logging.error("Error posting article ID %s: %s", article_id, e, exc_info=True)
        return None


def main():
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

            profile_id = open_and_maximize_profile(sequential_no)
            if not profile_id:
                logging.error("Failed to open profile with sequential_no %d, skipping article ID %s", sequential_no, article_id)
                failed_count += 1
                continue

            profile_no = get_profile_no(profile_id)
            profile_info = f"{profile_id} (No: {profile_no}, Seq: {sequential_no})"
            logging.info("Profile ready: %s", profile_info)

            time.sleep(2)

            try:
                url = post_article_to_medium(article, profile_id)

                if url:
                    update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                    posted_count += 1
                    logging.info("✓ Article ID %s posted successfully!", article_id)

                    minimize_profile_window(profile_no)
                    time.sleep(1)

                    logging.info("Closing profile after successful post...")
                    close_profile(profile_id)

                    time.sleep(2)
                else:
                    failed_count += 1
                    logging.error("✗ Failed to post article ID %s", article_id)
                    minimize_profile_window(profile_no)

            except Exception as e:
                logging.error("Error during posting process: %s", e, exc_info=True)
                failed_count += 1
                minimize_profile_window(profile_no)

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

