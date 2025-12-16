"""
Модели данных для постинга статей.
"""
from dataclasses import dataclass, field
from typing import Optional
from poster.settings import get_sequential_no


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


@dataclass
class Article:
    """Модель статьи для публикации"""
    id: int
    topic: str
    title: str
    body: str
    hashtags: list
    url: Optional[str] = None
    profile_id: Optional[int] = None


@dataclass
class PostResult:
    """Результат публикации статьи"""
    success: bool
    error_step: Optional[str] = None
    url: Optional[str] = None

