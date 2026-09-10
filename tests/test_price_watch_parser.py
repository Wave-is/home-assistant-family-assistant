"""Tests for the HTML price parser (no network I/O)."""

from __future__ import annotations

import pytest

from custom_components.family_assistant.price_watch_fetcher import (
    PriceFetchResult,
    _parse_availability,
    clean_url,
    parse_html,
)

# ── availability parsing ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://schema.org/InStock", "in_stock"),
        ("InStock", "in_stock"),
        ("instock", "in_stock"),
        ("OutOfStock", "out_of_stock"),
        ("https://schema.org/OutOfStock", "out_of_stock"),
        ("PreOrder", "preorder"),
        ("BackOrder", "backorder"),
        ("Discontinued", "discontinued"),
        ("SomethingUnknown", "unknown"),
        ("", "unknown"),
    ],
)
def test_parse_availability(raw, expected):
    assert _parse_availability(raw) == expected


# ── JSON-LD parsing ────────────────────────────────────────────────────────────


def _wrap_ld(data: dict) -> str:
    import json

    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def test_json_ld_product_in_stock_with_price():
    html = _wrap_ld(
        {
            "@type": "Product",
            "name": "Test TV",
            "offers": {
                "@type": "Offer",
                "price": "12999.00",
                "priceCurrency": "UAH",
                "availability": "https://schema.org/InStock",
            },
        }
    )
    result = parse_html(html)
    assert result.price_text == "12999.00"
    assert result.currency == "UAH"
    assert result.availability == "in_stock"
    assert result.error == ""


def test_json_ld_product_group():
    html = _wrap_ld(
        {
            "@type": "ProductGroup",
            "name": "Samsung Galaxy",
            "offers": [
                {
                    "@type": "Offer",
                    "price": "25000",
                    "priceCurrency": "UAH",
                    "availability": "https://schema.org/OutOfStock",
                }
            ],
        }
    )
    result = parse_html(html)
    assert result.availability == "out_of_stock"
    assert result.price_text == "25000"


def test_json_ld_graph_array():
    import json

    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "WebPage"},
                    {
                        "@type": "Product",
                        "offers": {
                            "price": "999",
                            "priceCurrency": "USD",
                            "availability": "InStock",
                        },
                    },
                ],
            }
        )
        + "</script>"
    )
    result = parse_html(html)
    assert result.price_text == "999"
    assert result.availability == "in_stock"


def test_json_ld_multiple_script_blocks_first_product_wins():
    """First Product block with offers should win."""
    import json

    block1 = (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "Organization", "name": "Shop"})
        + "</script>"
    )
    block2 = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "Product",
                "offers": {"price": "500", "priceCurrency": "UAH", "availability": "InStock"},
            }
        )
        + "</script>"
    )
    result = parse_html(block1 + block2)
    assert result.price_text == "500"


def test_json_ld_invalid_json_falls_through_to_fallback():
    html = (
        '<script type="application/ld+json">NOT JSON</script>'
        + '<p>Some content with "availability":"OutOfStock" inside</p>'
    )
    result = parse_html(html)
    assert result.availability == "out_of_stock"


def test_no_structured_data_returns_empty_result():
    html = "<html><body><p>Just a page with no product data.</p></body></html>"
    result = parse_html(html)
    assert result == PriceFetchResult()


def test_price_text_truncated_to_40_chars():

    long_price = "1" * 50
    html = _wrap_ld(
        {
            "@type": "Product",
            "offers": {"price": long_price, "priceCurrency": "UAH", "availability": "InStock"},
        }
    )
    result = parse_html(html)
    assert len(result.price_text) <= 40


# ── URL cleaning ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url,expected_fragment",
    [
        (
            "https://rozetka.com.ua/product/123?utm_source=google&utm_medium=cpc",
            "utm_source",
        ),
        (
            "https://example.com/p?_gl=abc123&price=100",
            "_gl",
        ),
        (
            "https://example.com/p?fbclid=XYZ&name=test",
            "fbclid",
        ),
    ],
)
def test_clean_url_removes_tracking_params(url, expected_fragment):
    cleaned = clean_url(url)
    assert expected_fragment not in cleaned


def test_clean_url_preserves_important_params():
    url = "https://example.com/search?q=laptop&page=2"
    cleaned = clean_url(url)
    assert "q=laptop" in cleaned
    assert "page=2" in cleaned


def test_clean_url_no_params_unchanged():
    url = "https://example.com/product/12345"
    assert clean_url(url) == url


# ── fallback availability regex ────────────────────────────────────────────────


def test_fallback_regex_finds_availability_in_plain_html():
    html = """
    <html>
    <body>
    <div class="product">
      <span itemprop="availability" content="https://schema.org/OutOfStock">Немає в наявності</span>
    </div>
    <script>var data = {"availability": "https://schema.org/OutOfStock"};</script>
    </body>
    </html>
    """
    result = parse_html(html)
    assert result.availability == "out_of_stock"
