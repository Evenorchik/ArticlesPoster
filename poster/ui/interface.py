"""
Абстракция для UI драйвера (Protocol для тестируемости).
"""
from typing import Protocol, Tuple


class UiDriver(Protocol):
    """Протокол для UI драйвера (можно заменить на мок для тестов)."""
    
    def click(self, x: int, y: int) -> None:
        """Кликнуть по координатам."""
        ...
    
    def hotkey(self, *keys: str) -> None:
        """Нажать комбинацию клавиш."""
        ...
    
    def press(self, key: str) -> None:
        """Нажать одну клавишу."""
        ...
    
    def write(self, text: str, interval: float = 0.0) -> None:
        """Ввести текст."""
        ...
    
    def sleep(self, seconds: float) -> None:
        """Пауза."""
        ...
    
    def screenshot_on_click(self, coords: Tuple[int, int], label: str = "") -> None:
        """Сделать скриншот перед кликом (для отладки)."""
        ...

