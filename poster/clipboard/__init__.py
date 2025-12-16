"""
Модули для работы с буфером обмена и конвертацией Markdown.
"""
from poster.clipboard.markdown_conv import markdown_to_html, html_to_plain_text
from poster.clipboard.richtext import copy_markdown_as_rich_text

__all__ = [
    'markdown_to_html',
    'html_to_plain_text',
    'copy_markdown_as_rich_text',
]

