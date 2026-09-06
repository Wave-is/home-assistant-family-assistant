"""Typed privilege commands and role-projected local wallet responses."""

import re

from ..domain.validation import DomainError

COPY = {
    "en": {
        "title": "Family privileges",
        "wallet": "Point wallet",
        "earned": "earned",
        "reserved": "reserved",
        "spent": "spent",
        "available": "available",
        "net": "net",
        "points": "points",
        "empty": "No privileges or requests.",
        "requested": "awaiting parent approval",
        "approved": "approved",
        "fulfilled": "marked provided by a parent",
        "rejected": "declined",
        "cancelled": "cancelled",
        "expired": "expired",
        "refunded": "points refunded",
        "more": "More details are in the court card.",
    },
    "ru": {
        "title": "Семейные привилегии",
        "wallet": "Кошелёк баллов",
        "earned": "начислено",
        "reserved": "резерв",
        "spent": "потрачено",
        "available": "доступно",
        "net": "остаток",
        "points": "баллов",
        "empty": "Привилегий и заявок нет.",
        "requested": "ждёт одобрения родителя",
        "approved": "одобрено",
        "fulfilled": "родитель отметил предоставление",
        "rejected": "отклонено",
        "cancelled": "отменено",
        "expired": "истекло",
        "refunded": "баллы возвращены",
        "more": "Подробности — в карточке суда.",
    },
    "uk": {
        "title": "Сімейні привілеї",
        "wallet": "Гаманець балів",
        "earned": "нараховано",
        "reserved": "резерв",
        "spent": "витрачено",
        "available": "доступно",
        "net": "залишок",
        "points": "балів",
        "empty": "Привілеїв і заявок немає.",
        "requested": "чекає схвалення батьків",
        "approved": "схвалено",
        "fulfilled": "батьки відзначили надання",
        "rejected": "відхилено",
        "cancelled": "скасовано",
        "expired": "термін минув",
        "refunded": "бали повернено",
        "more": "Подробиці — у картці суду.",
    },
}


def summary(record, language):
    t = COPY.get(language, COPY["en"])
    return f"{record['name']} · {record['cost']} {t['points']}" + (
        f" · {t[record['status']]}" if "status" in record else ""
    )


def help_text(language):
    name, points, reason = {
        "en": ("name", "points", "reason"),
        "ru": ("название", "баллы", "причина"),
        "uk": ("назва", "бали", "причина"),
    }.get(language, ("name", "points", "reason"))
    return (
        f"\n/rewards · /wallet\n/reward R000001\n/rewardadd {name} | {points}"
        f"\n/rewarddecide V000001 | approve/reject/cancel/fulfill/refund | {reason}"
    )


def read(view, language, *, only_wallet=False):
    if "court" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if view["role"] == "guest":
        raise DomainError("forbidden")
    t = COPY.get(language, COPY["en"])
    data = view.get("rewards", {})
    names = {m["id"]: m["name"] for m in view["members"]}
    lines = ["🎁 " + t["wallet" if only_wallet else "title"]]
    for row in data.get("balances", []):
        lines.append(
            names.get(row["member"], "—")
            + ": "
            + " · ".join(
                f"{t[k]} {row[k]}" for k in ("earned", "reserved", "spent", "available", "net")
            )
        )
    if not only_wallet:
        for record in data.get("catalog", []):
            if record["enabled"]:
                lines.append(f"{record['id']} · {summary(record, language)}")
        for record in data.get("requests", [])[-15:]:
            lines.append(
                f"{record['id']} · {names.get(record['member'], '—')} · {summary(record, language)}"
            )
    if len(lines) == 1:
        lines.append(t["empty"])
    # Telegram has no paginated text response; the card retains complete history.
    return "\n".join(lines)[:3400] + "\n" + t["more"]


def parsed(view, command, parts):
    if command not in {"/reward", "/rewardadd", "/rewarddecide"}:
        return None
    if command == "/rewardadd" and len(parts) in {2, 3}:
        if not re.fullmatch(r"\d{1,5}", parts[1]):
            raise DomainError("invalid_field", "cost")
        return "court.reward_save", {
            "name": parts[0],
            "cost": int(parts[1]),
            "description": parts[2] if len(parts) == 3 else "",
        }
    key = "catalog" if command == "/reward" else "requests"
    records = view.get("rewards", {}).get(key, [])
    record = next((r for r in records if r["id"] == parts[0].upper()), None)
    if not record:
        raise DomainError("not_found")
    payload = {"id": record["id"], "revision": record["revision"]}
    if command == "/reward" and len(parts) in {1, 2}:
        return "court.reward_request", {**payload, "note": parts[1] if len(parts) == 2 else ""}
    if command == "/rewarddecide" and len(parts) == 3:
        return "court.reward_transition", {**payload, "decision": parts[1], "reason": parts[2]}
    raise DomainError("invalid_field")
