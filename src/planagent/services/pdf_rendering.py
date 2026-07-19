from __future__ import annotations

import base64
import binascii
import html
import re
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import unquote_to_bytes, urlsplit

import markdown2

DEFAULT_MAX_PDF_DATA_URI_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_PDF_INLINE_RESOURCES = 16
DEFAULT_MAX_PDF_MARKDOWN_CHARS = 500_000
DEFAULT_MAX_PDF_OUTPUT_BYTES = 25 * 1024 * 1024
_PDF_DATA_URI_MIME_TYPES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/svg+xml",
        "image/webp",
    }
)
_PDF_RESOURCE_ATTRIBUTES = frozenset({"data", "href", "poster", "src", "srcset", "xlink:href"})
_PDF_CSS_URL_PATTERN = re.compile(r"url\s*\(", re.IGNORECASE)


class PdfPolicyViolation(ValueError):
    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def _reject_pdf_css_resources(css: str) -> None:
    if "\\" in css or "/*" in css or "*/" in css or _PDF_CSS_URL_PATTERN.search(css):
        raise PdfPolicyViolation("PDF CSS resource syntax is disabled")


class _PdfInlineResourceCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.count = 0
        self._style_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "style":
            self._style_depth += 1
        self._count_attributes(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._count_attributes(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            _reject_pdf_css_resources(data)

    def _count_attributes(self, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is None:
                continue
            lowered_name = name.lower()
            if lowered_name in _PDF_RESOURCE_ATTRIBUTES:
                self.count += value.lower().count("data:")
            if lowered_name == "style":
                _reject_pdf_css_resources(value)


def count_pdf_inline_resources(html_content: str) -> int:
    counter = _PdfInlineResourceCounter()
    counter.feed(html_content)
    counter.close()
    return counter.count


def safe_pdf_url_fetcher(
    url: str,
    timeout: int = 10,
    ssl_context: object | None = None,
    *,
    max_data_uri_bytes: int = DEFAULT_MAX_PDF_DATA_URI_BYTES,
) -> dict[str, Any]:
    if urlsplit(url).scheme.lower() != "data":
        raise PdfPolicyViolation("PDF external resources are disabled")

    metadata, separator, encoded_payload = url[5:].partition(",")
    if not separator:
        raise PdfPolicyViolation("PDF resources must be valid inline image data")
    metadata_parts = [part.strip().lower() for part in metadata.split(";")]
    media_type = metadata_parts[0] or "text/plain"
    if media_type not in _PDF_DATA_URI_MIME_TYPES:
        raise PdfPolicyViolation("PDF resources must be approved inline image data")

    if "base64" in metadata_parts[1:]:
        max_encoded_size = ((max_data_uri_bytes + 2) // 3) * 4
        if len(encoded_payload) > max_encoded_size:
            raise PdfPolicyViolation("PDF inline image exceeds the size limit", status_code=413)
        try:
            decoded_payload = base64.b64decode(encoded_payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PdfPolicyViolation("PDF resources must be valid inline image data") from exc
    else:
        if len(encoded_payload) > max_data_uri_bytes * 3:
            raise PdfPolicyViolation("PDF inline image exceeds the size limit", status_code=413)
        decoded_payload = unquote_to_bytes(encoded_payload)

    if len(decoded_payload) > max_data_uri_bytes:
        raise PdfPolicyViolation("PDF inline image exceeds the size limit", status_code=413)

    from weasyprint import default_url_fetcher

    return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)


def build_safe_pdf_url_fetcher(
    *,
    max_resources: int,
    url_fetcher: Callable[[str, int, object | None], dict[str, Any]],
) -> Callable[[str, int, object | None], dict[str, Any]]:
    resource_count = 0

    def restricted_fetcher(
        url: str,
        timeout: int = 10,
        ssl_context: object | None = None,
    ) -> dict[str, Any]:
        nonlocal resource_count
        resource_count += 1
        if resource_count > max_resources:
            raise PdfPolicyViolation("PDF contains too many inline resources", status_code=413)
        return url_fetcher(url, timeout, ssl_context)

    return restricted_fetcher


class MarkdownPdfRenderer:
    def __init__(
        self,
        *,
        max_markdown_chars: int = DEFAULT_MAX_PDF_MARKDOWN_CHARS,
        max_inline_resources: int = DEFAULT_MAX_PDF_INLINE_RESOURCES,
        max_output_bytes: int = DEFAULT_MAX_PDF_OUTPUT_BYTES,
        url_fetcher: Callable[[str, int, object | None], dict[str, Any]] = safe_pdf_url_fetcher,
    ) -> None:
        self.max_markdown_chars = max_markdown_chars
        self.max_inline_resources = max_inline_resources
        self.max_output_bytes = max_output_bytes
        self.url_fetcher = url_fetcher

    def render(self, md_content: str, title: str = "PlanAgent Report") -> bytes:
        if len(md_content) > self.max_markdown_chars:
            raise PdfPolicyViolation("PDF Markdown exceeds the size limit", status_code=413)

        import weasyprint

        safe_title = html.escape(str(title), quote=True)
        html_content = markdown2.markdown(
            md_content,
            extras=[
                "tables",
                "fenced-code-blocks",
                "code-friendly",
                "header-ids",
                "toc",
                "metadata",
            ],
        )
        if count_pdf_inline_resources(html_content) > self.max_inline_resources:
            raise PdfPolicyViolation("PDF contains too many inline resources", status_code=413)

        full_html = _wrap_pdf_html(html_content, safe_title)
        pdf_bytes = weasyprint.HTML(
            string=full_html,
            url_fetcher=build_safe_pdf_url_fetcher(
                max_resources=self.max_inline_resources,
                url_fetcher=self.url_fetcher,
            ),
        ).write_pdf(presentational_hints=False)
        if len(pdf_bytes) > self.max_output_bytes:
            raise PdfPolicyViolation("Generated PDF exceeds the size limit", status_code=413)
        return pdf_bytes


def _wrap_pdf_html(html_content: str, safe_title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>{safe_title}</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm 2.5cm;
            @top-center {{
                content: "PlanAgent";
                font-size: 9px;
                color: #666;
            }}
            @bottom-center {{
                content: "第 " counter(page) " 页";
                font-size: 9px;
                color: #666;
            }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            font-size: 11pt;
            line-height: 1.7;
            color: #1a1a2e;
        }}
        h1 {{
            color: #0f3460;
            border-bottom: 3px solid #0f3460;
            padding-bottom: 8px;
            font-size: 20pt;
            margin-top: 30px;
        }}
        h2 {{
            color: #16213e;
            border-bottom: 1px solid #ddd;
            padding-bottom: 5px;
            font-size: 15pt;
            margin-top: 25px;
        }}
        h3 {{
            color: #1a1a2e;
            font-size: 12pt;
            margin-top: 18px;
        }}
        ul, ol {{ padding-left: 25px; }}
        li {{ margin-bottom: 4px; }}
        blockquote {{
            border-left: 4px solid #0f3460;
            margin: 12px 0;
            padding: 8px 16px;
            background: #f8f9fa;
            color: #333;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 12px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{ background: #0f3460; color: white; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        code {{
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10pt;
        }}
        pre {{
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
        }}
        pre code {{ background: none; padding: 0; color: #e0e0e0; }}
        strong {{ color: #0f3460; }}
        a {{ color: #0f3460; text-decoration: none; }}
        hr {{ border: none; border-top: 2px solid #eee; margin: 20px 0; }}
        em {{ color: #555; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
