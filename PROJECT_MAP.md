# PROJECT MAP - ArticlesPoster

**ОСНОВНОЙ WORKFLOW ПОСТИНГА СТАТЕЙ**

Этот файл описывает архитектуру основного workflow автоматического постинга статей на Medium и Quora. Файлы для создания контента (article_creation.py, humanizing.py, generate_cover_images.py) не включены в эту карту.

---

## 📋 ОБЗОР СИСТЕМЫ

**ArticlesPoster** - система автоматического постинга SEO-оптимизированных статей на Medium и Quora:
- **Автоматизация**: PyAutoGUI для UI-автоматизации, Selenium для управления браузером
- **Управление профилями**: Ads Power API для работы с профилями браузера
- **Хранилище**: PostgreSQL для хранения статей и метаданных
- **Уведомления**: Telegram бот для мониторинга процесса
- **Платформы**: Medium и Quora с поддержкой обложек

---

## 🎯 ГЛАВНЫЙ ОРКЕСТРАТОР

### `scheduled_poster.py` - Основной скрипт постинга

**Назначение:** Автоматический постинг статей на Medium и Quora по расписанию с распределением по профилям.

**Логика работы:**
- **Четные дни месяца** → профили 1-5 (sequential_no)
- **Нечетные дни месяца** → профили 6-10 (sequential_no)
- **Время постинга** (Kiev time):
  - Medium: из `TIME_CONFIG["MEDIUM_START"]` до `TIME_CONFIG["MEDIUM_END"]`
  - Quora: из `TIME_CONFIG["QUORA_START"]` до `TIME_CONFIG["QUORA_END"]`
- **Распределение статей:**
  - 4 статьи с `is_link='no'` (для каждой платформы)
  - 1 статья с `is_link='yes'` (для каждой платформы)
  - Случайное распределение по профилям с минимум 10 минут между постами

**Основной процесс:**
1. Подключение к PostgreSQL
2. Выбор таблицы `refined_articles_*`
3. Выбор платформы (Medium, Quora, или обе)
4. Определение профилей для сегодня (`get_profiles_for_today()`)
5. Генерация расписания постинга (`generate_posting_schedule()`)
6. Получение статей из БД по фильтру `is_link`
7. Распределение статей по профилям
8. Отправка уведомления в Telegram о запуске
9. Для каждой статьи:
   - Ожидание до времени постинга (`wait_until_time()`)
   - Замена ссылок для статей с `is_link='yes'` (`update_article_body_with_replaced_link()`)
   - Открытие профиля Ads Power (`open_ads_power_profile()`)
   - Публикация статьи (`post_article_to_medium()` или `post_article_to_quora()`)
   - Получение URL опубликованной статьи
   - Обновление БД (url, profile_id)
   - Отправка уведомления в Telegram
   - Минимизация/закрытие профиля
10. Отправка уведомления о завершении
11. Ожидание до следующего дня и повтор цикла

**Ключевые функции:**
- `open_ads_power_profile(profile_id, platform)` - открытие профиля и подготовка вкладки
- `post_article_to_medium(article, profile_id)` - публикация на Medium
- `post_article_to_quora(article, profile_id)` - публикация на Quora
- `get_profiles_for_today()` - определение профилей для сегодняшнего дня
- `generate_posting_schedule()` - генерация расписания с временами
- `wait_until_time(target_time)` - ожидание до указанного времени
- `get_articles_by_is_link(pg_conn, table_name, is_link, limit)` - получение статей по фильтру
- `log_summary()` - сокращенное логирование (режим SUMMARY)
- `close_profile(profile_id)` - закрытие профиля

**Зависимости:**
- `poster.db` - работа с БД
- `poster.settings` - настройки профилей и URL
- `poster.adspower` - управление профилями
- `poster.ui` - UI автоматизация
- `poster.medium` - постинг на Medium
- `poster.quora` - постинг на Quora
- `poster.link_replacer` - замена ссылок
- `poster.models` - модели данных
- `config.py` - конфигурация
- `telegram_bot.py` - уведомления

---

## 📁 МОДУЛЬНАЯ АРХИТЕКТУРА

### `poster/` - Основной пакет модулей

#### **База данных** (`poster/db/`)

**`poster/db/postgres.py`**
- `get_pg_conn()` - подключение к PostgreSQL
- `get_refined_articles_tables(pg_conn)` - список таблиц `refined_articles_*`
- `ensure_profile_id_column(pg_conn, table_name)` - создание колонки `profile_id` если нет
- `parse_id_selection(selection_str)` - парсинг выбора статей (например "1,2,3" или "1-5")
- `get_articles_to_post(pg_conn, table_name, article_ids=None)` - получение статей для публикации
- `update_article_url_and_profile(pg_conn, table_name, article_id, url, profile_no)` - обновление URL и profile_id

**`poster/db/__init__.py`** - экспорт всех функций БД

**Используется в:** `scheduled_poster.py`

---

#### **Настройки** (`poster/settings.py`)

**Содержит:**
- `MEDIUM_NEW_STORY_URL` - URL страницы создания статьи на Medium
- `QUORA_URL` - URL главной страницы Quora
- `ADS_POWER_API_URL` - URL API Ads Power (локальный)
- `ADS_POWER_API_KEY` - ключ API Ads Power
- `PROFILE_MAPPING` - словарь {profile_id: profile_no}
- `PROFILE_SEQUENTIAL_MAPPING` - словарь {profile_no: sequential_no (1-10)}
- `PROFILE_IDS` - список всех profile_id
- Функции маппинга:
  - `get_profile_no(profile_id)` - получить profile_no по profile_id
  - `get_profile_id(profile_no)` - получить profile_id по profile_no
  - `get_sequential_no(profile_no)` - получить sequential_no по profile_no
  - `get_profile_id_by_sequential_no(sequential_no)` - получить profile_id по sequential_no
  - `get_profile_no_by_sequential_no(sequential_no)` - получить profile_no по sequential_no

**Используется в:** `scheduled_poster.py`, всех модулях AdsPower, модулях постинга

---

#### **Управление профилями Ads Power** (`poster/adspower/`)

**`poster/adspower/api_client.py`**
- `AdsPowerApiClient` - HTTP-клиент для Ads Power API
- `start_profile(profile_id)` - запуск профиля через API
- `stop_profile(profile_id)` - остановка профиля
- `get_active_info(profile_id)` - получение статуса профиля (Active, ws.selenium, webdriver_path)
- `wait_for_ready(profile_id, timeout_s)` - ожидание готовности профиля

**`poster/adspower/selenium_attach.py`**
- `attach_driver(active_info)` - подключение Selenium WebDriver к профилю
- `SELENIUM_AVAILABLE` - флаг доступности Selenium

**`poster/adspower/profile_manager.py`**
- `ProfileManager` - менеджер для кэширования и управления профилями
- `ensure_ready(profile_no)` - подготовка профиля (Active + Selenium + tag tab)
- Хранит кэш профилей в `self.profiles: Dict[int, Profile]`

**`poster/adspower/window_manager.py`**
- `WindowManager` - управление окнами браузера
- `focus(profile)` - фокус и максимизация окна профиля
- `minimize(profile)` - минимизация окна

**`poster/adspower/tabs.py`**
- `TabManager` - управление вкладками браузера
- `ensure_tag_tab(profile)` - создание/поддержание tag-вкладки (стабильный маркер окна)
- `ensure_medium_tab(profile)` - открытие/поддержание вкладки Medium new-story
- `ensure_quora_tab(profile)` - открытие/поддержание вкладки Quora
- `safe_switch_to(driver, handle)` - безопасное переключение на вкладку
- `find_existing_medium_tab(profile)` - поиск существующей вкладки Medium
- `find_existing_quora_tab(profile)` - поиск существующей вкладки Quora

**`poster/adspower/__init__.py`** - экспорт всех классов и функций

**Используется в:** `scheduled_poster.py`

---

#### **UI Автоматизация** (`poster/ui/`)

**`poster/ui/pyautogui_driver.py`**
- `PyAutoGuiDriver` - обертка над PyAutoGUI для автоматизации UI
- Методы: `click()`, `hotkey()`, `press()`, `write()`, `sleep()`, `screenshot_on_click()`
- Интеграция с `click_debug_screenshots.py` для отладки

**`poster/ui/coords.py`**
- `Coords` - координаты для кликов на экране
  - Medium: `TITLE_INPUT`, `PUBLISH_BUTTON_1`, `HASHTAGS_INPUT`, `PUBLISH_BUTTON_2`, `BODY_TEXT`, `PLUS_BUTTON`, `IMAGE_BUTTON`
  - Quora: `QUORA_EMPTY_CLICK`, `QUORA_CREATE_POST`, `QUORA_TEXT_FIELD`, `QUORA_IMAGE_UPLOAD`, `QUORA_POST_BUTTON`
- `Delays` - задержки между действиями
  - Medium: `AFTER_OPEN_TAB`, `AFTER_TITLE_CLICK`, `AFTER_TITLE_PASTE`, `AFTER_ENTER`, `AFTER_BODY_PASTE`, `AFTER_PUBLISH_1`, `AFTER_HASHTAGS_CLICK`, `BETWEEN_HASHTAGS`, `AFTER_PUBLISH_2`
  - Quora: `QUORA_AFTER_OPEN_TAB`, `QUORA_AFTER_EMPTY_CLICK`, `QUORA_AFTER_CREATE_POST`, `QUORA_AFTER_TEXT_FIELD`, `QUORA_AFTER_IMAGE_UPLOAD`, `QUORA_AFTER_POST`

**`poster/ui/interface.py`**
- `UiDriver` - Protocol для абстракции UI драйвера (для тестируемости)

**`poster/ui/__init__.py`** - экспорт `PyAutoGuiDriver`, `Coords`, `Delays`, `UiDriver`

**Используется в:** `poster/medium/poster_flow.py`, `poster/quora/poster_flow.py`

---

#### **Буфер обмена** (`poster/clipboard/`)

**`poster/clipboard/richtext.py`**
- `copy_markdown_as_rich_text(markdown_text)` - копирование Markdown в буфер обмена как HTML (CF_HTML формат)
- `HtmlClipboard` - класс для работы с HTML форматом в буфере обмена Windows
- Использует `markdown_to_html()` для конвертации

**`poster/clipboard/markdown_conv.py`**
- `markdown_to_html(markdown_text)` - конвертация Markdown в HTML
- `html_to_plain_text(html)` - конвертация HTML в plain text

**`poster/clipboard/__init__.py`** - экспорт функций

**Используется в:** `poster/medium/poster_flow.py`, `poster/quora/poster_flow.py`

---

#### **Постинг на Medium** (`poster/medium/`)

**`poster/medium/poster_flow.py`**
- `publish_article(ui, article, coords, delays, clipboard_copy_rich_text=None)` - полный UI-поток публикации на Medium
- **Шаги:**
  1. Перезагрузка страницы (F5)
  2. Клик на поле title
  3. Вставка title
  4. Нажатие Enter
  5. Вставка body как Rich Text (HTML)
  6. Клик на первую кнопку Publish
  7. Клик на поле hashtags
  8. Вставка hashtags (по одному, с запятыми)
  9. Клик на финальную кнопку Publish

**`poster/medium/url_fetcher.py`**
- `fetch_published_url(profile, ui)` - извлечение URL опубликованной статьи на Medium
- Использует PyAutoGUI для копирования URL из адресной строки

**`poster/medium/__init__.py`** - экспорт `publish_article`, `fetch_published_url`

**Используется в:** `scheduled_poster.py` → `post_article_to_medium()`

---

#### **Постинг на Quora** (`poster/quora/`)

**`poster/quora/poster_flow.py`**
- `publish_article(ui, article, coords, delays, driver, images_root_dir, clipboard_copy_rich_text=None)` - полный UI-поток публикации на Quora
- **Шаги:**
  1. Ожидание после открытия вкладки
  2. Пустой клик для гарантии фокуса
  3. Клик на кнопку "Create post"
  4. Клик на текстовое поле
  5. Вставка title (с очисткой поля)
  6. Нажатие Enter
  7. Вставка body как Rich Text (HTML)
  8. Клик на кнопку загрузки изображения (с ESC для закрытия Windows диалога)
  9. Прикрепление обложки через Selenium (если есть)
  10. Клик на кнопку Post

**`poster/quora/cover_attacher.py`**
- `attach_cover_image(driver, cover_image_name, images_root_dir, article_id)` - прикрепление обложки через Selenium
- `resolve_cover_image_path(cover_image_name, images_root_dir)` - резолвинг пути к файлу обложки
- Ищет `input[type="file"]` элемент и отправляет путь через `send_keys()`

**`poster/quora/url_fetcher.py`**
- `fetch_published_url(profile, ui)` - извлечение URL опубликованной статьи на Quora
- Использует PyAutoGUI для копирования URL из адресной строки

**`poster/quora/__init__.py`** - экспорт `publish_article`, `fetch_published_url`

**Используется в:** `scheduled_poster.py` → `post_article_to_quora()`

---

#### **Вспомогательные модули**

**`poster/models.py`**
- `Profile` - dataclass для хранения информации о профиле Ads Power
  - `profile_no`, `profile_id`, `driver`, `window_tag`, `medium_window_handle`, `quora_window_handle`, `sequential_no`, `tag_window_handle`
- `Article` - модель статьи (не используется напрямую в workflow)
- `PostResult` - результат публикации (не используется напрямую в workflow)

**`poster/timing.py`**
- `random_delay(base_seconds, variance_percent)` - случайная задержка с вариацией
- `wait_with_log(seconds, step_name, variance_percent)` - ожидание с логированием

**`poster/link_replacer.py`**
- `update_article_body_with_replaced_link(pg_conn, table_name, article_id, sequential_no)` - замена ссылок Bonza Chat на реферальные для статей с `is_link='yes'`
- Использует маппинг `sequential_no → referral_code` для генерации реферальных ссылок

**`poster/__init__.py`** - корневой пакет (пустой)

---

## ⚙️ КОНФИГУРАЦИЯ

### `config.py`
**Содержит:**
- `OPENAI_API_KEY` - ключ API OpenAI
- `OPENAI_MODEL` - модель для структурирования
- `OPENAI_MODEL_THINKING` - модель для перефразирования
- `OPENAI_MODEL_COVER_PROMPT` - модель для генерации промпта обложки
- `OPENAI_IMAGE_MODEL` - модель для генерации изображений
- `POSTGRES_DSN` - строка подключения к PostgreSQL
- `HUMANIZER_URL` - URL сервиса humanizer (используется в humanizing.py, не в основном workflow)
- Координаты для PyAutoGUI (используются в humanizing.py, не в основном workflow)
- `LOG_LEVEL` - уровень логирования ("DEBUG", "INFO")
- `LOG_MODE` - режим логирования для scheduled_poster ("DEBUG" | "SUMMARY")
- `TIME_CONFIG` - настройки времени постинга:
  - `MEDIUM_START` - начало постинга на Medium (формат "HH:MM")
  - `MEDIUM_END` - конец постинга на Medium
  - `QUORA_START` - начало постинга на Quora
  - `QUORA_END` - конец постинга на Quora

**Используется в:** Всех модулях проекта

### `config_bot.py`
**Содержит:**
- `TELEGRAM_BOT_TOKEN` - токен бота от @BotFather

**Используется в:** `telegram_bot.py`

---

## 📢 УВЕДОМЛЕНИЯ

### `telegram_bot.py`
**Функции:**
- `notify_poster_started(platform, articles_count, schedule_info)` - уведомление о запуске постинга
- `notify_article_posted(platform, article_topic, article_title, hashtags, url)` - уведомление о публикации статьи
- `notify_posting_complete(platform, posted_count, failed_count)` - уведомление о завершении постинга
- `send_message(message, parse_mode="HTML")` - базовая отправка сообщения
- `load_subscribers()`, `save_subscribers()` - управление подписчиками

**Используется в:** `scheduled_poster.py`

---

## 🔄 ПОТОК ДАННЫХ В ОСНОВНОМ WORKFLOW

```
1. scheduled_poster.py запускается
   └─> Подключение к PostgreSQL
   └─> Выбор таблицы refined_articles_*
   └─> Выбор платформы (Medium/Quora/Both)

2. Определение профилей и расписания
   └─> get_profiles_for_today() - профили 1-5 или 6-10
   └─> generate_posting_schedule() - случайные времена постинга

3. Получение статей из БД
   └─> get_articles_by_is_link(is_link='no', limit=4)
   └─> get_articles_by_is_link(is_link='yes', limit=1)

4. Для каждой статьи:
   ├─> wait_until_time() - ожидание времени постинга
   ├─> update_article_body_with_replaced_link() - если is_link='yes'
   ├─> open_ads_power_profile() - открытие профиля
   │   └─> ProfileManager.ensure_ready() - подготовка профиля
   │   └─> TabManager.ensure_medium_tab() или ensure_quora_tab()
   │   └─> WindowManager.focus() - фокус окна
   ├─> post_article_to_medium() или post_article_to_quora()
   │   ├─> poster.medium.publish_article() или poster.quora.publish_article()
   │   │   ├─> PyAutoGuiDriver - UI автоматизация
   │   │   ├─> copy_markdown_as_rich_text() - вставка body
   │   │   └─> attach_cover_image() - для Quora (если есть обложка)
   │   └─> fetch_published_url() - получение URL
   ├─> update_article_url_and_profile() - обновление БД
   ├─> notify_article_posted() - уведомление в Telegram
   └─> close_profile() - закрытие профиля

5. notify_posting_complete() - уведомление о завершении
6. Ожидание до следующего дня и повтор цикла
```

---

## 🔗 ЗАВИСИМОСТИ МЕЖДУ МОДУЛЯМИ

```
scheduled_poster.py (главный оркестратор)
├──> poster.db - работа с БД
├──> poster.settings - настройки профилей
├──> poster.adspower - управление профилями
│   ├──> api_client - HTTP клиент Ads Power
│   ├──> selenium_attach - подключение Selenium
│   ├──> profile_manager - кэш профилей
│   ├──> window_manager - управление окнами
│   └──> tabs - управление вкладками
├──> poster.ui - UI автоматизация
│   ├──> pyautogui_driver - обертка PyAutoGUI
│   └──> coords - координаты и задержки
├──> poster.medium - постинг на Medium
│   ├──> poster_flow - UI поток публикации
│   └──> url_fetcher - получение URL
├──> poster.quora - постинг на Quora
│   ├──> poster_flow - UI поток публикации
│   ├──> cover_attacher - прикрепление обложки
│   └──> url_fetcher - получение URL
├──> poster.clipboard - работа с буфером обмена
│   ├──> richtext - Rich Text форматирование
│   └──> markdown_conv - конвертация Markdown
├──> poster.timing - утилиты времени
├──> poster.link_replacer - замена ссылок
├──> poster.models - модели данных
├──> config.py - конфигурация
└──> telegram_bot.py - уведомления
```

---

## 📊 СТРУКТУРА БАЗЫ ДАННЫХ

### Таблица `refined_articles_<N>` (N - номер итерации)

**Поля:**
- `id` (BIGSERIAL, PRIMARY KEY) - ID статьи
- `topic` (TEXT) - тема статьи
- `title` (TEXT) - заголовок
- `body` (TEXT) - тело статьи (Markdown)
- `links` (TEXT) - ссылки в статье
- `keywords` (TEXT) - ключевые слова
- `hashtag1`, `hashtag2`, `hashtag3`, `hashtag4` (TEXT) - хэштеги
- `hashtag5` (TEXT) - опциональный хэштег
- `url` (TEXT) - URL опубликованной статьи (заполняется после публикации)
- `approval` (TEXT) - статус одобрения
- `is_link` (TEXT) - "yes" или "no" (наличие встроенной ссылки)
- `created_at` (TIMESTAMPTZ) - дата создания
- `profile_id` (INTEGER) - ID профиля, который опубликовал статью (заполняется после публикации)
- `cover_image_name` (TEXT) - имя файла обложки (например "cover_image_1.jpg")

---

## 🎯 КЛЮЧЕВЫЕ КОНЦЕПЦИИ

### Профили Ads Power
- **profile_id** - уникальный ID профиля в Ads Power (например "kqnfhbe")
- **profile_no** - внутренний номер профиля (например 70)
- **sequential_no** - порядковый номер 1-10 для ротации

**Маппинг:**
- `PROFILE_MAPPING`: {profile_id → profile_no}
- `PROFILE_SEQUENTIAL_MAPPING`: {profile_no → sequential_no}

### Типы статей
- **is_link='no'** - стандартная статья без встроенной ссылки
- **is_link='yes'** - статья с встроенной ссылкой на bonza.chat (заменяется на реферальную перед постингом)

### Платформы
- **Medium** - постинг через PyAutoGUI, поддержка hashtags
- **Quora** - постинг через PyAutoGUI, поддержка обложек через Selenium

---

## 🛠️ ТЕХНОЛОГИИ

- **Python 3.x**
- **PostgreSQL** - основное хранилище статей
- **PyAutoGUI** - автоматизация UI (клики, вставка текста)
- **Selenium** - управление браузером через Ads Power
- **Ads Power API** - управление профилями браузера
- **Telegram Bot API** - уведомления
- **Windows Clipboard API** - работа с Rich Text (CF_HTML)

---

## 📝 ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **Координаты PyAutoGUI** - зависят от разрешения экрана и браузера, могут требовать обновления
2. **Ads Power** - должен быть запущен локально на порту 50325
3. **Профили** - должны быть настроены в Ads Power с соответствующими profile_id
4. **Время постинга** - настроено на Kiev time (Europe/Kiev)
5. **Обложки** - хранятся в `./data/images/`, прикрепляются через Selenium для Quora
6. **Markdown форматирование** - статьи сохраняются с Markdown, конвертируются в HTML при публикации
7. **Реферальные ссылки** - генерируются на основе sequential_no профиля для статей с is_link='yes'

---

## 🚀 ЗАПУСК СИСТЕМЫ

### Автоматический постинг по расписанию:
```bash
python scheduled_poster.py
# Выбираем таблицу refined_articles_N
# Выбираем платформу (Medium/Quora/Both)
# Система автоматически:
#   - Определяет профили для сегодня
#   - Генерирует расписание
#   - Распределяет статьи
#   - Публикует по расписанию
#   - Ждет до следующего дня и повторяет цикл
```

---

## 🔍 ПОИСК ФУНКЦИЙ

**Работа с БД:**
- `get_pg_conn()` - `poster/db/postgres.py`
- `get_refined_articles_tables()` - `poster/db/postgres.py`
- `get_articles_to_post()` - `poster/db/postgres.py`
- `update_article_url_and_profile()` - `poster/db/postgres.py`

**Работа с профилями:**
- `open_ads_power_profile()` - `scheduled_poster.py`
- `ProfileManager.ensure_ready()` - `poster/adspower/profile_manager.py`
- `TabManager.ensure_medium_tab()` - `poster/adspower/tabs.py`
- `TabManager.ensure_quora_tab()` - `poster/adspower/tabs.py`
- `WindowManager.focus()` - `poster/adspower/window_manager.py`
- `close_profile()` - `scheduled_poster.py`

**Публикация:**
- `post_article_to_medium()` - `scheduled_poster.py`
- `post_article_to_quora()` - `scheduled_poster.py`
- `publish_article()` - `poster/medium/poster_flow.py` или `poster/quora/poster_flow.py`
- `fetch_published_url()` - `poster/medium/url_fetcher.py` или `poster/quora/url_fetcher.py`

**Расписание:**
- `get_profiles_for_today()` - `scheduled_poster.py`
- `generate_posting_schedule()` - `scheduled_poster.py`
- `wait_until_time()` - `scheduled_poster.py`

**Замена ссылок:**
- `update_article_body_with_replaced_link()` - `poster/link_replacer.py`

---

**Последнее обновление:** 2025-12-21  
**Версия:** 2.0 (модульная архитектура)
