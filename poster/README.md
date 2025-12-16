# Poster Package - Модульная структура

Этот пакет содержит модульную структуру для постинга статей на Medium.

## Структура

```
poster/
├── __init__.py
├── settings.py          # Константы и настройки
├── models.py            # Модели данных (Profile, Article, PostResult)
├── timing.py            # Утилиты для задержек
├── db/                  # Работа с PostgreSQL
│   ├── __init__.py
│   └── postgres.py
├── clipboard/           # Работа с буфером обмена
│   ├── __init__.py
│   ├── markdown_conv.py
│   └── richtext.py
├── ui/                  # UI драйверы (PyAutoGUI)
│   ├── __init__.py
│   ├── interface.py     # Протокол UiDriver
│   ├── pyautogui_driver.py
│   └── coords.py        # Координаты и задержки
├── adspower/            # Работа с Ads Power
│   ├── __init__.py
│   ├── api_client.py    # HTTP клиент для API
│   ├── selenium_attach.py
│   ├── profile_manager.py
│   ├── window_manager.py
│   └── tabs.py          # Управление вкладками
├── medium/              # Работа с Medium.com
│   ├── __init__.py
│   ├── poster_flow.py   # UI-поток публикации
│   └── url_fetcher.py   # Получение URL
└── cli/                 # CLI интерфейс
    └── manual_poster.py
```

## Использование

### Базовый пример

```python
from poster.cli.manual_poster import main

if __name__ == "__main__":
    main()
```

### Программное использование

```python
from poster.db import get_pg_conn, get_articles_to_post
from poster.adspower import ProfileManager, WindowManager, TabManager
from poster.ui import PyAutoGuiDriver, Coords, Delays
from poster.medium import publish_article, fetch_published_url

# Инициализация
api_client = AdsPowerApiClient()
profile_manager = ProfileManager(api_client)
window_manager = WindowManager()
tab_manager = TabManager()
ui = PyAutoGuiDriver()
coords = Coords()
delays = Delays()

# Открыть профиль
profile = profile_manager.ensure_ready(profile_no)
window_manager.focus(profile)
tab_manager.ensure_medium_tab_open(profile, ui, window_manager)

# Опубликовать статью
success = publish_article(ui, article, coords, delays)
if success:
    url = fetch_published_url(profile, ui)
```

## Преимущества модульной структуры

1. **Тестируемость**: Каждый модуль можно тестировать изолированно
2. **Заменяемость**: UI драйвер можно заменить на мок для тестов
3. **Читаемость**: Каждый модуль отвечает за свою область
4. **Дебаг**: Легко локализовать проблемы по модулям

## Миграция с medium_poster.py

Старый `medium_poster.py` можно заменить на `poster/cli/manual_poster.py`:

```bash
python -m poster.cli.manual_poster
```

Или создать алиас:

```python
# medium_poster.py (legacy wrapper)
from poster.cli.manual_poster import main

if __name__ == "__main__":
    main()
```

