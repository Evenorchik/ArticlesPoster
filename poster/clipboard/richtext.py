"""
Работа с Rich Text в буфере обмена (CF_HTML формат).
"""
import logging
import pyperclip
from poster.clipboard.markdown_conv import markdown_to_html


class HtmlClipboard:
    """Класс для работы с HTML форматом в буфере обмена Windows."""
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
        """Получить формат CF_HTML для Windows clipboard."""
        import win32clipboard
        if cls.CF_HTML is None:
            cls.CF_HTML = win32clipboard.RegisterClipboardFormat("HTML Format")
        return cls.CF_HTML

    @classmethod
    def put_fragment(cls, fragment: str, source: str = "about:blank") -> None:
        """Поместить HTML фрагмент в буфер обмена в формате CF_HTML."""
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
    """Скопировать Markdown текст в буфер обмена как Rich Text (HTML)."""
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

