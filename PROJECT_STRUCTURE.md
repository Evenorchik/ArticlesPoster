# СТРУКТУРА ПРОЕКТА ArticlesPoster

Визуальное представление структуры файлов и папок проекта.

---

```
ArticlesPoster/
│
├── 📄 scheduled_poster.py          ⭐ ГЛАВНЫЙ ОРКЕСТРАТОР
│                                      Автоматический постинг по расписанию
│
├── 📁 poster/                       📦 ОСНОВНОЙ ПАКЕТ МОДУЛЕЙ
│   │
│   ├── 📄 __init__.py              📦 Корневой пакет
│   ├── 📄 models.py                 📋 Модели данных (Profile, Article, PostResult)
│   ├── 📄 settings.py               ⚙️ Настройки профилей и URL
│   ├── 📄 timing.py                 ⏱️ Утилиты времени (задержки)
│   ├── 📄 link_replacer.py          🔗 Замена ссылок на реферальные
│   │
│   ├── 📁 db/                       💾 РАБОТА С БАЗОЙ ДАННЫХ
│   │   ├── 📄 __init__.py           📦 Экспорт функций БД
│   │   └── 📄 postgres.py           🔌 Подключение и запросы к PostgreSQL
│   │
│   ├── 📁 adspower/                 🌐 УПРАВЛЕНИЕ ПРОФИЛЯМИ ADS POWER
│   │   ├── 📄 __init__.py           📦 Экспорт модулей AdsPower
│   │   ├── 📄 api_client.py        🔌 HTTP клиент для Ads Power API
│   │   ├── 📄 selenium_attach.py    🔗 Подключение Selenium WebDriver
│   │   ├── 📄 profile_manager.py    👤 Менеджер профилей (кэш)
│   │   ├── 📄 window_manager.py     🪟 Управление окнами браузера
│   │   └── 📄 tabs.py               📑 Управление вкладками (Medium, Quora, tag)
│   │
│   ├── 📁 ui/                       🖱️ UI АВТОМАТИЗАЦИЯ
│   │   ├── 📄 __init__.py           📦 Экспорт UI модулей
│   │   ├── 📄 interface.py          🔌 Protocol для UI драйвера
│   │   ├── 📄 pyautogui_driver.py   🎮 Обертка над PyAutoGUI
│   │   └── 📄 coords.py             📍 Координаты кликов и задержки
│   │
│   ├── 📁 clipboard/                📋 БУФЕР ОБМЕНА
│   │   ├── 📄 __init__.py           📦 Экспорт функций clipboard
│   │   ├── 📄 richtext.py           📝 Rich Text форматирование (CF_HTML)
│   │   └── 📄 markdown_conv.py      🔄 Конвертация Markdown ↔ HTML
│   │
│   ├── 📁 medium/                   📰 ПОСТИНГ НА MEDIUM
│   │   ├── 📄 __init__.py           📦 Экспорт функций Medium
│   │   ├── 📄 poster_flow.py        🔄 UI поток публикации на Medium
│   │   └── 📄 url_fetcher.py        🔗 Получение URL опубликованной статьи
│   │
│   ├── 📁 quora/                    💬 ПОСТИНГ НА QUORA
│   │   ├── 📄 __init__.py           📦 Экспорт функций Quora
│   │   ├── 📄 poster_flow.py        🔄 UI поток публикации на Quora
│   │   ├── 📄 cover_attacher.py     🖼️ Прикрепление обложки через Selenium
│   │   └── 📄 url_fetcher.py        🔗 Получение URL опубликованной статьи
│   │
│   └── 📁 cli/                      💻 КОМАНДНАЯ СТРОКА
│       └── 📄 manual_poster.py      ✋ Ручной постер (альтернатива scheduled_poster)
│
├── 📄 config.py                     ⚙️ ОСНОВНАЯ КОНФИГУРАЦИЯ
│                                      API ключи, DSN, время постинга, координаты
│
├── 📄 config_bot.py                 🤖 КОНФИГУРАЦИЯ TELEGRAM БОТА
│                                      Токен бота
│
├── 📄 telegram_bot.py               📢 TELEGRAM УВЕДОМЛЕНИЯ
│                                      Отправка уведомлений о постинге
│
├── 📄 telegram_bot_listener.py      👂 СЛУШАТЕЛЬ TELEGRAM БОТА
│                                      Фоновый бот для добавления подписчиков
│
├── 📄 telegram_subscriber_manager.py 👥 МЕНЕДЖЕР ПОДПИСЧИКОВ
│                                      Утилита для управления подписчиками
│
├── 📄 click_debug_screenshots.py    📸 ОТЛАДКА КЛИКОВ
│                                      Скриншоты с отметками координат
│
├── 📄 quora_pyautogui_unit_testing.py  🧪 ТЕСТЕР QUORA
│                                         Юнит-тестер для постинга на Quora
│
├── 📄 test_medium_image_upload.py   🧪 ТЕСТЕР ЗАГРУЗКИ ИЗОБРАЖЕНИЙ
│                                      Тест загрузки обложек на Medium
│
├── 📄 pyautogui_unit_testing.py     🧪 ОБЩИЙ ТЕСТЕР PYAutoGUI
│                                      Общий тестер PyAutoGUI (устаревший)
│
├── 📄 profile_open_unit_testing.py  🧪 ТЕСТЕР ПРОФИЛЕЙ
│                                      Тест открытия профилей Ads Power
│
├── 📄 clean_body_text.py            🧹 ОЧИСТКА ТЕКСТА
│                                      Очистка колонки body от нежелательных элементов
│
├── 📄 generate_cover_images.py      🎨 ГЕНЕРАЦИЯ ОБЛОЖЕК
│                                      Генерация обложек через GPT-Image 1.5 API
│
├── 📄 humanizing.py                 ✍️ ГУМАНИЗАЦИЯ СТАТЕЙ
│                                      Обработка статей через GPT Humanizer
│
├── 📄 article_creation.py            📝 СОЗДАНИЕ СТАТЕЙ
│                                      Генерация статей через Anthropic Claude API
│
├── 📄 prompts.py                    📋 ПРОМПТЫ ДЛЯ AI
│                                      Промпты для генерации и обработки контента
│
├── 📄 keywords.txt                   🔑 КЛЮЧЕВЫЕ СЛОВА
│                                      Список SEO ключевых слов
│
├── 📄 requirements.txt               📦 ЗАВИСИМОСТИ PYTHON
│                                      Список пакетов для установки
│
├── 📄 .gitignore                    🚫 ИГНОРИРУЕМЫЕ ФАЙЛЫ
│                                      Файлы для игнорирования Git
│
├── 📄 README.md                     📖 ДОКУМЕНТАЦИЯ
│                                      Основная документация проекта
│
├── 📄 PROJECT_MAP.md                🗺️ КАРТА ПРОЕКТА
│                                      Детальное описание основного workflow
│
├── 📄 PROJECT_STRUCTURE.md          📁 СТРУКТУРА ПРОЕКТА (этот файл)
│                                      Визуальное представление структуры
│
├── 📄 medium_poster.py              ⚠️ УСТАРЕВШИЙ ПОСТЕР
│                                      Старый скрипт (заменен модульной архитектурой)
│
└── 📁 data/                         📂 ДАННЫЕ
    └── 📁 images/                   🖼️ ОБЛОЖКИ СТАТЕЙ
        └── cover_image_*.jpg        📷 Файлы обложек
```

---

## 📊 ЛЕГЕНДА

- ⭐ **ГЛАВНЫЙ ОРКЕСТРАТОР** - основной файл для запуска системы
- 📦 **ПАКЕТ/МОДУЛЬ** - Python пакет или модуль
- ⚙️ **КОНФИГУРАЦИЯ** - файлы настроек
- 💾 **БАЗА ДАННЫХ** - работа с БД
- 🌐 **ADS POWER** - управление профилями браузера
- 🖱️ **UI** - автоматизация пользовательского интерфейса
- 📋 **CLIPBOARD** - работа с буфером обмена
- 📰 **MEDIUM** - модули для постинга на Medium
- 💬 **QUORA** - модули для постинга на Quora
- 📢 **TELEGRAM** - уведомления
- 🧪 **ТЕСТЫ** - тестовые скрипты
- ⚠️ **УСТАРЕВШИЙ** - файл не используется в основном workflow
- 📖 **ДОКУМЕНТАЦИЯ** - документация проекта
- 🧹 **УТИЛИТЫ** - вспомогательные скрипты

---

## 🎯 ОСНОВНОЙ WORKFLOW

**Активные файлы в основном workflow:**

1. **scheduled_poster.py** - главный оркестратор
2. **poster/db/** - работа с БД
3. **poster/settings.py** - настройки
4. **poster/adspower/** - управление профилями
5. **poster/ui/** - UI автоматизация
6. **poster/clipboard/** - буфер обмена
7. **poster/medium/** - постинг на Medium
8. **poster/quora/** - постинг на Quora
9. **poster/link_replacer.py** - замена ссылок
10. **poster/models.py** - модели данных
11. **poster/timing.py** - утилиты времени
12. **config.py** - конфигурация
13. **config_bot.py** - конфигурация бота
14. **telegram_bot.py** - уведомления

**Не в основном workflow:**
- Файлы создания контента (article_creation.py, humanizing.py, generate_cover_images.py)
- Тестовые скрипты (quora_pyautogui_unit_testing.py, test_medium_image_upload.py и т.д.)
- Устаревшие файлы (medium_poster.py)
- Утилиты (clean_body_text.py, telegram_bot_listener.py и т.д.)

---

**Последнее обновление:** 2025-12-21

