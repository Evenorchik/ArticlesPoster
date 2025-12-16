"""
Конвертация Markdown в HTML и обратно.
"""
import logging
import re

# Markdown
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logging.warning("Markdown not available. Install with: pip install markdown")


def markdown_to_html(markdown_text: str) -> str:
    """Конвертировать Markdown в HTML."""
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
    """Конвертировать HTML в простой текст."""
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

