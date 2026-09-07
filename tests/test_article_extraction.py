"""Bounded article text extraction without network access."""

import pytest

from custom_components.family_assistant.assistant.article import (
    MAX_BODY_BYTES,
    MAX_TEXT_CHARS,
    extract,
)
from custom_components.family_assistant.domain.validation import DomainError


def test_html_extracts_visible_text_and_title_without_active_or_hidden_content():
    body = b"""
      <!doctype html><html><head><title> A &amp; B </title>
      <style>SECRET_STYLE</style></head><body>
      <nav>Visible navigation</nav><main><h1>Heading</h1>
      <p>First &amp; second.</p><script>SECRET_SCRIPT</script>
      <svg><text>SECRET_SVG</text></svg><form>SECRET_FORM<input value='x'></form>
      <template>SECRET_TEMPLATE</template><ul><li>One</li><li>Two</li></ul></main>
      </body></html>
    """
    result = extract(body, "text/html", "utf-8")
    assert result["title"] == "A & B"
    assert "Heading\n\nFirst & second." in result["text"]
    assert "One\nTwo" in result["text"]
    assert "Visible navigation" in result["text"]
    for secret in ("SECRET_STYLE", "SECRET_SCRIPT", "SECRET_SVG", "SECRET_FORM", "SECRET_TEMPLATE"):
        assert secret not in result["text"]


def test_html_never_returns_embedded_urls_as_separate_metadata_or_executes_markup():
    result = extract(
        b"<html><body><p>&lt;img src=x onerror=alert(1)&gt;</p>"
        b'<iframe src="http://127.0.0.1/private">hidden</iframe>'
        b'<a href="https://other.invalid">Label only</a></body></html>',
        "text/html",
    )
    assert result == {
        "title": "",
        "text": "<img src=x onerror=alert(1)>\nLabel only",
    }
    assert set(result) == {"title", "text"}


@pytest.mark.parametrize(
    "charset,value,encoded",
    [
        (None, "Привіт", "Привіт".encode()),
        ("US-ASCII", "plain", b"plain"),
        ("windows-1251", "Привет", "Привет".encode("cp1251")),
        ("ISO-8859-1", "caf\xe9", b"caf\xe9"),
    ],
)
def test_plain_text_uses_only_bounded_supported_charsets(charset, value, encoded):
    assert extract(encoded, "text/plain", charset) == {"title": "", "text": value}


@pytest.mark.parametrize(
    "body,content_type,charset,code",
    [
        (b"", "text/plain", None, "article_invalid_content"),
        (b"\xff", "text/plain", "utf-8", "article_invalid_content"),
        (b"hello", "application/xhtml+xml", None, "article_unsupported"),
        (b"hello", "text/plain", "utf-16", "article_unsupported"),
        (b" " * 20, "text/plain", None, "article_invalid_content"),
    ],
    ids=["empty", "bad-utf8", "xhtml", "charset", "whitespace"],
)
def test_invalid_binary_empty_unsupported_and_oversized_content_fails_closed(
    body, content_type, charset, code
):
    with pytest.raises(DomainError, match=code):
        extract(body, content_type, charset)


@pytest.mark.parametrize("size", [MAX_BODY_BYTES + 1, MAX_TEXT_CHARS + 1])
def test_oversized_raw_or_extracted_plain_text_is_rejected(size):
    with pytest.raises(DomainError, match="article_too_large"):
        extract(b"x" * size, "text/plain")


def test_html_text_overflow_is_rejected_instead_of_silently_truncated():
    body = ("<p>" + "a" * (MAX_TEXT_CHARS + 1) + "</p>").encode()
    with pytest.raises(DomainError, match="article_too_large"):
        extract(body, "text/html")


def test_control_characters_and_whitespace_are_normalized_deterministically():
    assert extract(b" one\x00 \t two\r\n\r\n\r\n three ", "text/plain") == {
        "title": "",
        "text": "one two\n\nthree",
    }
