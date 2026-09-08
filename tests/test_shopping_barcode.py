"""Optional structural GTIN metadata never guesses a product or changes quantities."""

import pytest
from test_shopping_edit import edit_payload
from test_shopping_series_engine import payload as series_payload

from custom_components.family_assistant.domain.gtin import normalize_gtin
from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.parametrize(
    "value, expected",
    [
        ("96385074", "00000096385074"),
        ("036000291452", "00036000291452"),
        ("0036000291452", "00036000291452"),
        (" 4006381333931 ", "04006381333931"),
        ("10012345000017", "10012345000017"),
        ("", ""),
        ("  ", ""),
    ],
)
def test_gtin_shapes_and_mod10(value, expected):
    assert normalize_gtin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        96385074,
        [],
        {},
        "00000000",
        "00000000000000",
        "96385075",
        "036000291451",
        "9638-5074",
        "9638 5074",
        "٩٦٣٨٥٠٧٤",
        "123456789",
        "x4006381333931",
    ],
)
def test_gtin_rejects_malformed_or_wrong_checksum(value):
    with pytest.raises(DomainError, match="invalid_field"):
        normalize_gtin(value)


@pytest.mark.asyncio
async def test_add_exact_replay_purchase_history_edit_clear_and_amounts(engine, now):
    payload = {"name": "Fictional cereal", "quantity": 3, "barcode": "036000291452"}
    item = await engine.execute("parent", "shopping.add", payload, "barcode-add", now)
    assert item["barcode"] == "00036000291452"
    assert await engine.execute("parent", "shopping.add", payload, "barcode-add", now) == item
    assert item["history"][0]["detail"]["barcode"] == item["barcode"]
    purchased = await engine.execute(
        "parent",
        "shopping.purchase",
        {"id": item["id"], "revision": item["revision"], "quantity": 1},
        "barcode-buy",
        now,
    )
    changed = await engine.execute(
        "parent",
        "shopping.edit",
        edit_payload(purchased, barcode="4006381333931"),
        "barcode-edit",
        now,
    )
    assert changed["quantity"] == 3 and changed["purchased"] == 1
    assert changed["history"][1]["detail"]["barcode"] == "00036000291452"
    assert changed["history"][-1]["detail"] == {"fields": ["barcode"], "barcode": "04006381333931"}
    cleared = await engine.execute(
        "parent", "shopping.edit", edit_payload(changed, barcode=""), "barcode-clear", now
    )
    assert cleared["barcode"] == "" and cleared["purchased"] == 1


@pytest.mark.asyncio
async def test_barcode_child_proposal_keeps_parent_approval_and_invalid_input_is_atomic(
    engine, now
):
    item = await engine.execute(
        "child",
        "shopping.add",
        {"name": "Fictional milk", "barcode": "96385074"},
        "child-code",
        now,
    )
    assert item["status"] == "pending"
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            "child",
            "shopping.purchase",
            {"id": item["id"], "revision": item["revision"]},
            "no-approval",
            now,
        )
    with pytest.raises(DomainError):
        await engine.execute(
            "parent", "shopping.add", {"name": "Bad code", "barcode": "96385075"}, "bad-code", now
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_merge_requires_same_gtin_even_when_every_other_field_matches(engine, now):
    items = []
    for index, barcode in enumerate(["036000291452", "0036000291452", "4006381333931", ""]):
        items.append(
            await engine.execute(
                "parent",
                "shopping.add",
                {"name": "Same name", "barcode": barcode},
                f"code-{index}",
                now,
            )
        )
    target = items[0]
    for other in items[2:]:
        before = engine.snapshot()
        with pytest.raises(DomainError, match="conflict"):
            await engine.execute(
                "parent",
                "shopping.merge",
                {
                    "id": target["id"],
                    "revision": target["revision"],
                    "sources": [{"id": other["id"], "revision": other["revision"]}],
                },
                "wrong-" + other["id"],
                now,
            )
        assert engine.snapshot() == before
    merged = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": target["id"],
            "revision": target["revision"],
            "sources": [{"id": items[1]["id"], "revision": items[1]["revision"]}],
        },
        "same-code",
        now,
    )
    assert merged["barcode"] == "00036000291452" and merged["quantity"] == 2


@pytest.mark.asyncio
async def test_legacy_no_barcode_item_unchanged_edit_is_still_denied(engine, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Plain item"}, "plain", now)
    assert "barcode" not in item
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent", "shopping.edit", edit_payload(item, barcode=""), "plain-noop", now
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_recurring_barcode_survives_edit_tick_reload_and_clear(engine, store, now):
    from custom_components.family_assistant.domain.engine import Engine

    series = await engine.execute(
        "parent",
        "shopping.series_save",
        series_payload(now, barcode="96385074"),
        "series-code",
        now,
    )
    changed = await engine.execute(
        "parent",
        "shopping.series_save",
        {
            "id": series["id"],
            "revision": series["revision"],
            "name": "Other label",
            "rule": series["rule"],
        },
        "series-keep",
        now,
    )
    assert changed["barcode"] == "00000096385074"
    restarted = Engine(engine.snapshot(), store.save)
    await restarted.tick(now)
    item = next(iter(restarted.snapshot()["shopping"].values()))
    assert item["barcode"] == changed["barcode"]
    assert item["history"][0]["detail"]["barcode"] == changed["barcode"]
    current = restarted.snapshot()["shopping_series"][series["id"]]
    cleared = await restarted.execute(
        "parent",
        "shopping.series_save",
        {
            "id": series["id"],
            "revision": current["revision"],
            "name": current["name"],
            "rule": current["rule"],
            "barcode": "",
        },
        "series-clear",
        now,
    )
    assert cleared["barcode"] == ""
    assert restarted.snapshot()["shopping"][item["id"]]["barcode"] == changed["barcode"]
    before = restarted.snapshot()
    with pytest.raises(DomainError):
        await restarted.execute(
            "parent",
            "shopping.series_save",
            series_payload(now, barcode="96385075"),
            "invalid-series",
            now,
        )
    assert restarted.snapshot() == before
