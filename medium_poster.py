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
COORDS_TITLE_INPUT = (516, 215)        # Шаг 3: ввод текста (title)
COORDS_PUBLISH_BUTTON_1 = (1180, 119)  # Шаг 7: первая кнопка Publish
COORDS_HASHTAGS_INPUT = (941, 392)     # Шаг 8: поле ввода хэштегов
COORDS_PUBLISH_BUTTON_2 = (925, 553)   # Шаг 10: финальная кнопка Publish

# Задержки (базовые значения, будут рандомизированы)
WAIT_AFTER_OPEN_TAB = 10   # Шаг 2: ждём 10 секунд после открытия вкладки
WAIT_AFTER_TITLE_CLICK = 1 # Шаг 3: ждём 1 секунду после клика на поле title
WAIT_AFTER_TITLE_PASTE = 1 # Шаг 4: ждём 1 секунду после вставки title
WAIT_AFTER_ENTER = 1       # Шаг 5: ждём 1 секунду после Enter
WAIT_AFTER_BODY_PASTE = 1  # Шаг 6: ждём 1 секунду после вставки body
WAIT_AFTER_PUBLISH_1 = 3   # Шаг 7: ждём 3 секунды после первой кнопки Publish
WAIT_AFTER_HASHTAGS_CLICK = 1  # Шаг 8: ждём 1 секунду после клика на поле хэштегов
WAIT_BETWEEN_HASHTAGS = 1      # Шаг 9: ждём 1 секунду между хэштегами
WAIT_AFTER_PUBLISH_2 = 15      # Шаг 10: ждём 15 секунд после финальной кнопки Publish
WAIT_AFTER_COPY = 1            # Шаг 12: ждём 1 секунду после Ctrl+C

# Настройка PyAutoGUI
pyautogui.PAUSE = 0.1
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
    
    logging.debug("Checking for hashtag5 column...")
    check_col_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'hashtag5'
    """)
    
    with pg_conn.cursor() as cur:
        cur.execute(check_col_query, (table_name,))
        has_hashtag5 = cur.fetchone() is not None
        logging.info("Table has hashtag5 column: %s", has_hashtag5)
    
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
            cur.execute(query, params)
            articles = cur.fetchall()
            logging.info("Fetched %d article(s) from database", len(articles))
            if articles:
                logging.debug("Article IDs: %s", [a['id'] if isinstance(a, dict) else a[0] for a in articles[:10]])
            return articles
    except Exception as e:
        logging.error("Error fetching articles: %s", e)
        logging.error("Query: %s", query.as_string(pg_conn) if hasattr(query, 'as_string') else str(query))
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


def markdown_to_html(markdown_text: str) -> str:
    """
    Конвертирует Markdown в HTML-фрагмент.
    """
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
    """
    Извлекает plain text из HTML (убирает все теги).
    """
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


# ==========================
# Правильный CF_HTML через HtmlClipboard
# ==========================

class HtmlClipboard:
    """
    Минимальная реализация CF_HTML по рецепту HtmlClipboard (ActiveState/Gist).
    Используется только для записи HTML в буфер обмена как 'HTML Format'.
    """
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
        """
        Кладёт HTML-фрагмент в буфер как 'HTML Format' (CF_HTML).
        """
        import win32clipboard

        html = cls.DEFAULT_HTML_BODY % fragment
        fragment_start = html.index(fragment)
        fragment_end = fragment_start + len(fragment)

        # selection == fragment
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
    """
    Markdown → HTML → CF_HTML в буфере обмена.

    Если всё прошло ок, возвращает True.
    Medium / Chrome при Ctrl+V должны вставить форматированный текст.
    """
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
        logging.debug("  Using API key for authentication")
    
    try:
        logging.debug("  GET request to: %s with params: %s", endpoint, params)
        response = requests.get(endpoint, params=params, headers=headers, timeout=10)
        logging.debug("  Response status code: %s", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            logging.debug("  Response data: %s", data)
            
            if data.get("code") == 0:
                profile_data = data.get("data", {})
                status = profile_data.get("status", "Unknown")
                logging.info("Profile ID %s (No: %s) status: %s", profile_id, profile_no, status)
                return profile_data
            else:
                error_msg = data.get("msg", "Unknown error")
                logging.debug("  API returned error: %s", error_msg)
                return None
        else:
            logging.debug("  HTTP error: %s", response.status_code)
            return None
            
    except requests.exceptions.RequestException as e:
        logging.error("✗ Request error checking profile status: %s", e)
        return None
    except Exception as e:
        logging.error("✗ Unexpected error checking profile status: %s", e)
        return None


def ensure_profile_ready(profile_no: int) -> bool:
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
    
    if profile.driver:
        try:
            profile.driver.current_url
            logging.debug("Profile %d already has active driver", profile_no)
            return True
        except:
            logging.debug("Profile %d driver is dead, recreating...", profile_no)
            profile.driver = None
    
    profile_status = check_ads_power_profile_status(profile.profile_id)
    
    if not profile_status:
        logging.info("Profile %d (ID: %s) is not active, starting...", profile_no, profile.profile_id)
        
        endpoint = f"{ADS_POWER_API_URL}/api/v2/browser-profile/start"
        headers = {"Content-Type": "application/json"}
        if ADS_POWER_API_KEY:
            headers["Authorization"] = f"Bearer {ADS_POWER_API_KEY}"
        
        payload = {"profile_id": profile.profile_id}
        
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
            if response.status_code != 200:
                logging.error("Failed to start profile %d: HTTP %d", profile_no, response.status_code)
                return False
            
            data = response.json()
            if data.get("code") != 0:
                logging.error("Failed to start profile %d: %s", profile_no, data.get("msg", "Unknown error"))
                return False
            
            time.sleep(3)
            
            profile_status = check_ads_power_profile_status(profile.profile_id)
            if not profile_status:
                logging.error("Profile %d still not active after start", profile_no)
                return False
        except Exception as e:
            logging.error("Error starting profile %d: %s", profile_no, e)
            return False
    
    ws_data = profile_status.get("ws", {})
    selenium_address = ws_data.get("selenium", "")
    webdriver_path = profile_status.get("webdriver", "")
    
    if not selenium_address or not webdriver_path:
        logging.error("Missing selenium address or webdriver path for profile %d", profile_no)
        return False
    
    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", selenium_address)
        
        service = Service(webdriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        try:
            driver.maximize_window()
            time.sleep(0.5)
        except Exception as max_err:
            logging.debug("  Window already maximized (or maximize failed): %s", max_err)
            time.sleep(0.2)
        
        try:
            all_handles = driver.window_handles
            if all_handles:
                driver.switch_to.window(all_handles[0])
                driver.get("about:blank")
                driver.execute_script(f"document.title = '{profile.window_tag}';")
                time.sleep(0.5)
            else:
                driver.get("about:blank")
                driver.execute_script(f"document.title = '{profile.window_tag}';")
                time.sleep(0.5)
        except Exception as tag_err:
            logging.warning("  Failed to set window_tag: %s, but continuing...", tag_err)
        
        profile.driver = driver
        logging.info(
            "✓ Profile %d (ID: %s) ready with window_tag: %s",
            profile_no, profile.profile_id, profile.window_tag
        )
        return True
        
    except Exception as e:
        logging.error("Error creating Selenium driver for profile %d: %s", profile_no, e)
        return False


def focus_profile_window(profile_no: int) -> bool:
    if profile_no not in profiles:
        logging.error("Profile %d not found in profiles dict", profile_no)
        return False
    
    profile = profiles[profile_no]
    
    try:
        import pygetwindow as gw
        
        windows = gw.getWindowsWithTitle(profile.window_tag)
        if not windows:
            all_windows = gw.getAllWindows()
            for win in all_windows:
                if profile.window_tag in win.title:
                    windows = [win]
                    break
        
        if not windows:
            logging.warning("Window with tag '%s' not found for profile %d", profile.window_tag, profile_no)
            return False
        
        win = windows[0]
        
        if win.isMinimized:
            win.restore()
            time.sleep(0.3)
        
        win.activate()
        time.sleep(0.3)
        win.maximize()
        time.sleep(0.5)
        
        logging.info("✓ Profile %d window focused and maximized: %s", profile_no, win.title)
        return True
        
    except ImportError:
        logging.error("pygetwindow not available")
        return False
    except Exception as e:
        logging.error("Error focusing window for profile %d: %s", profile_no, e)
        return False


def minimize_profile_window(profile_no: int) -> bool:
    if profile_no not in profiles:
        return False
    
    profile = profiles[profile_no]
    
    try:
        import pygetwindow as gw
        
        windows = gw.getWindowsWithTitle(profile.window_tag)
        if not windows:
            all_windows = gw.getAllWindows()
            for win in all_windows:
                if profile.window_tag in win.title:
                    windows = [win]
                    break
        
        if windows:
            windows[0].minimize()
            logging.debug("Profile %d window minimized", profile_no)
            return True
        
        return False
    except:
        return False


def open_ads_power_profile(profile_id: str) -> Optional[str]:
    profile_no = get_profile_no(profile_id)
    sequential_no = get_sequential_no(profile_no)
    profile_info = f"{profile_id} (No: {profile_no}" + (f", Seq: {sequential_no})" if sequential_no else ")")
    logging.info("Opening/activating Ads Power profile: %s", profile_info)
    
    if not ensure_profile_ready(profile_no):
        logging.error("Failed to ensure profile %d is ready", profile_no)
        return None
    
    if not focus_profile_window(profile_no):
        logging.warning("Failed to focus window for profile %d, but continuing...", profile_no)
    
    logging.info("Opening Medium URL in active browser window via Selenium...")
    try:
        profile = profiles[profile_no]
        if not profile.driver:
            logging.error("Driver not available for profile %d", profile_no)
            return None
        
        all_handles = profile.driver.window_handles
        logging.debug("  Available window handles: %s", all_handles)
        
        if not all_handles:
            logging.error("  No window handles available!")
            return None
        
        try:
            target_handle = None
            for handle in all_handles:
                profile.driver.switch_to.window(handle)
                try:
                    title = profile.driver.title
                    if profile.window_tag in title:
                        target_handle = handle
                        break
                except:
                    pass
            
            if target_handle:
                profile.driver.switch_to.window(target_handle)
                logging.debug("  Switched to window with tag: %s", profile.window_tag)
            else:
                profile.driver.switch_to.window(all_handles[0])
                logging.debug("  Switched to first available window")
        except Exception as switch_err:
            logging.warning("  Failed to switch window: %s, using current window", switch_err)
        
        logging.info("  Navigating to Medium URL: %s", MEDIUM_NEW_STORY_URL)
        try:
            profile.driver.get(MEDIUM_NEW_STORY_URL)
            time.sleep(3)
        except Exception as nav_err:
            logging.error("  Failed to navigate to Medium URL: %s", nav_err)
            return None
        
        profile.medium_window_handle = profile.driver.current_window_handle
        logging.info("  Medium window handle saved: %s", profile.medium_window_handle)
        
        logging.info("  Activating browser window to make Medium tab visible...")
        try:
            focus_profile_window(profile_no)
            time.sleep(0.5)
            logging.info("  Browser window activated, Medium tab should be visible")
        except Exception as e:
            logging.warning("  Failed to activate window: %s, but continuing...", e)
        
        try:
            current_url = profile.driver.current_url
            logging.info("  Current URL: %s", current_url)
            
            if 'medium.com' not in current_url:
                logging.warning("  URL doesn't contain 'medium.com', retrying...")
                profile.driver.get(MEDIUM_NEW_STORY_URL)
                time.sleep(3)
                current_url = profile.driver.current_url
                logging.info("  Current URL after retry: %s", current_url)
                profile.medium_window_handle = profile.driver.current_window_handle
        except Exception as url_err:
            logging.warning("  Failed to get current URL: %s, but continuing...", url_err)
        
        logging.info("Waiting 10 seconds for page to load before starting PyAutoGUI cycle...")
        wait_with_log(WAIT_AFTER_OPEN_TAB, "Page load wait", 10.0)
        
        logging.info("✓ URL opened in AdsPower profile browser via Selenium, page loaded")
    except Exception as e:
        logging.error("Failed to open URL in AdsPower browser via Selenium: %s", e, exc_info=True)
        return None
    
    return profile_id


def post_article_to_medium(article: dict, profile_id: str) -> Optional[str]:
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
        
        # ======== ВАЖНО: вставка body только через Clipboard CF_HTML ========
        logging.info("STEP 5: Pasting body as Rich Text (HTML via CF_HTML)...")
        logging.info("  Body length: %d characters", len(body))
        
        time.sleep(1.5)  # даём Medium переключить фокус в body
        
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
            pyautogui.click(*COORDS_PUBLISH_BUTTON_2)
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
                except:
                    all_windows = profile.driver.window_handles
                    for window in all_windows:
                        profile.driver.switch_to.window(window)
                        current_url = profile.driver.current_url
                        if 'medium.com' in current_url and '/@' in current_url:
                            profile.medium_window_handle = window
                            break
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
        
        profile_index = 0
        posted_count = 0
        failed_count = 0
        
        for article in unpublished_articles:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            
            profile_id = PROFILE_IDS[profile_index % len(PROFILE_IDS)]
            profile_no = get_profile_no(profile_id)
            profile_index += 1
            
            logging.info("")
            logging.info("="*60)
            sequential_no = get_sequential_no(profile_no)
            profile_info = f"{profile_id} (No: {profile_no}" + (f", Seq: {sequential_no})" if sequential_no else ")")
            logging.info("Processing article ID %s with profile: %s", article_id, profile_info)
            logging.info("="*60)
            
            result = open_ads_power_profile(profile_id)
            if not result:
                sequential_no = get_sequential_no(profile_no)
                profile_info = f"{profile_id} (No: {profile_no}" + (f", Seq: {sequential_no})" if sequential_no else ")")
                logging.error("Failed to open profile: %s, skipping article ID %s", profile_info, article_id)
                failed_count += 1
                continue
            
            time.sleep(5)
            
            try:
                url = post_article_to_medium(article, profile_id)
                
                if url:
                    update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                    posted_count += 1
                    logging.info("✓ Article ID %s posted successfully!", article_id)
                else:
                    failed_count += 1
                    logging.error("✗ Failed to post article ID %s", article_id)
                
                minimize_profile_window(profile_no)
                
            finally:
                pass
            
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

