"""Private Telegram interaction descriptors for local family polls."""

from __future__ import annotations

import re
from datetime import datetime

from ..domain import poll_reviews
from ..domain import polls as poll_domain
from ..domain.validation import DomainError, fields, text, timestamp
from ..domain.validation import revision as strict_revision

MAX_RENDERED_POLLS = 8
MAX_MESSAGE_TEXT = 3800
MAX_KEYBOARD_BUTTONS = 100

COPY = {
    "en": {
        "title": "Family polls",
        "private": "Polls are private. Open a direct chat with me to view or vote.",
        "empty": "No polls are open and no closed results are available.",
        "more": "More polls are not shown. Reopen /polls to refresh the list.",
        "closes": "closes",
        "closed": "closed",
        "votes": "votes",
        "vote": "Vote",
        "revote": "Change vote",
        "close": "Close poll",
        "archive": "Archive poll",
        "review_vote": "Review your private vote",
        "review_close": "Review closing this poll",
        "review_archive": "Review archiving this poll",
        "not_anonymous": (
            "Ballots are private from family views, but this is not an anonymous survey."
        ),
        "confirm": "Confirm",
        "cancel": "Cancel",
        "saved_vote": "Vote recorded. Reopen /polls to see the current poll.",
        "saved_close": "Poll closed.",
        "saved_archive": "Poll archived.",
        "cancelled": "Poll action cancelled.",
    },
    "ru": {
        "title": "Семейные голосования",
        "private": "Голосования доступны только в личном чате. Откройте личный чат со мной.",
        "empty": "Открытых голосований и доступных закрытых результатов нет.",
        "more": "Показаны не все голосования. Снова откройте /polls, чтобы обновить список.",
        "closes": "закрывается",
        "closed": "закрыто",
        "votes": "голосов",
        "vote": "Голосовать",
        "revote": "Изменить голос",
        "close": "Закрыть голосование",
        "archive": "Архивировать",
        "review_vote": "Проверьте свой личный голос",
        "review_close": "Проверьте закрытие голосования",
        "review_archive": "Проверьте архивацию голосования",
        "not_anonymous": "Голоса скрыты в семейных представлениях, но это не анонимный опрос.",
        "confirm": "Подтвердить",
        "cancel": "Отмена",
        "saved_vote": "Голос записан. Откройте /polls, чтобы увидеть текущее состояние.",
        "saved_close": "Голосование закрыто.",
        "saved_archive": "Голосование архивировано.",
        "cancelled": "Действие с голосованием отменено.",
    },
    "uk": {
        "title": "Сімейні голосування",
        "private": "Голосування доступні лише в особистому чаті. Відкрийте особистий чат зі мною.",
        "empty": "Відкритих голосувань і доступних закритих результатів немає.",
        "more": "Показані не всі голосування. Знову відкрийте /polls, щоб оновити список.",
        "closes": "закривається",
        "closed": "закрито",
        "votes": "голосів",
        "vote": "Голосувати",
        "revote": "Змінити голос",
        "close": "Закрити голосування",
        "archive": "Архівувати",
        "review_vote": "Перевірте свій особистий голос",
        "review_close": "Перевірте закриття голосування",
        "review_archive": "Перевірте архівацію голосування",
        "not_anonymous": "Голоси приховані в сімейних поданнях, але це не анонімне опитування.",
        "confirm": "Підтвердити",
        "cancel": "Скасувати",
        "saved_vote": "Голос записано. Відкрийте /polls, щоб побачити поточний стан.",
        "saved_close": "Голосування закрито.",
        "saved_archive": "Голосування архівовано.",
        "cancelled": "Дію з голосуванням скасовано.",
    },
}

_SELECT = re.compile(r"ps:(v|c|a):(PL\d{6,12})(?::(O(?:10|[1-9])))?\Z")
_REVIEW = re.compile(r"pr:([yn]):(PR[A-Za-z0-9_-]{16})\Z")


def _copy(language: str) -> dict:
    return COPY.get(language, COPY["en"])


def _callback(value: str) -> str:
    if not isinstance(value, str) or len(value.encode()) > 64:
        raise DomainError("invalid_field", "callback")
    return value


def _descriptor(mode: str, **values) -> dict:
    return {"kind": "polls", "mode": mode, **values}


def _parse_selection(content: str) -> tuple[str, str, str | None]:
    match = _SELECT.fullmatch(_callback(content))
    if match is None:
        raise DomainError("invalid_field", "callback")
    kind = {"v": "vote", "c": "close", "a": "archive"}[match[1]]
    option_id = match[3]
    if (kind == "vote") != (option_id is not None):
        raise DomainError("invalid_field", "callback")
    return kind, match[2], option_id


def _parse_review(content: str) -> tuple[bool, str]:
    match = _REVIEW.fullmatch(_callback(content))
    if match is None:
        raise DomainError("invalid_field", "callback")
    return match[1] == "y", match[2]


async def route(
    engine,
    actor: str,
    content: str,
    operation_id: str,
    now: datetime,
    *,
    private: bool,
) -> dict | None:
    """Route only explicit poll commands; returned descriptors contain no poll text."""
    timestamp(now, "now")
    operation_id = text(operation_id, "operation_id", 180)
    if not isinstance(content, str):
        return None
    normalized = content.casefold().strip()
    if normalized == "/polls":
        return _descriptor("list") if private else _descriptor("private")
    if not (content.startswith("ps:") or content.startswith("pr:")):
        return None
    if not private:
        return _descriptor("private")
    if content.startswith("ps:"):
        kind, poll_id, option_id = _parse_selection(content)

        def create(ctx):
            return poll_reviews.begin(ctx, actor, kind, poll_id, option_id, operation_id)

        result = await engine.system_update("poll_review", now, create)
        return _descriptor("review", review_id=result["review_id"])

    confirmed, review_id = _parse_review(content)
    if not confirmed:

        def cancel(ctx):
            poll_reviews.cancel(ctx, actor, review_id, operation_id)

        await engine.system_update("poll_review_cancel", now, cancel)
        return _descriptor("cancelled")

    def claim(ctx):
        return poll_reviews.claim(ctx, actor, review_id, operation_id)

    action, payload, canonical_operation = await engine.system_update(
        "poll_review_claim", now, claim
    )
    await engine.execute(actor, action, payload, canonical_operation, now)

    def complete(ctx):
        poll_reviews.complete(ctx, actor, review_id, canonical_operation)

    await engine.system_update("poll_review_complete", now, complete)
    return _descriptor("saved", action=action.split(".", 1)[1])


def _button(label: str, callback_data: str) -> dict:
    return {"text": label, "callback_data": _callback(callback_data)}


def _poll_row(projection: dict, poll_id: str) -> dict | None:
    return next(
        (
            row
            for bucket in ("open", "closed")
            for row in projection.get(bucket, [])
            if row.get("id") == poll_id
        ),
        None,
    )


def _list_reply(projection: dict, language: str) -> dict:
    t = _copy(language)
    lines = [t["title"]]
    keyboard = []
    rows = projection.get("open", []) + projection.get("closed", [])
    rendered = 0
    for poll_number, row in enumerate(rows[:MAX_RENDERED_POLLS], 1):
        prefix = f"P{poll_number}"
        options = row.get("options", [])
        block_lines = ["", f"{prefix} · {text(row.get('question'), 'question', 240)}"]
        block_keyboard = []
        for index, option in enumerate(options, 1):
            label = text(option.get("label"), "option", 120)
            block_lines.append(f"{index}. {label}")
        if row.get("status") == "open":
            block_lines.append(f"{t['closes']}: {row['closes_at']}")
            if row.get("can_vote") is True:
                buttons = [
                    _button(
                        f"{prefix} · {index}. {text(option.get('label'), 'option', 120)[:48]}",
                        f"ps:v:{row['id']}:{option['id']}",
                    )
                    for index, option in enumerate(options, 1)
                ]
                block_keyboard.extend(
                    buttons[index : index + 2] for index in range(0, len(buttons), 2)
                )
            if row.get("can_close") is True:
                block_keyboard.append([_button(f"{prefix} · {t['close']}", f"ps:c:{row['id']}")])
        else:
            counts = {result.get("option_id"): result.get("count") for result in row["results"]}
            block_lines = block_lines[:2]
            block_lines.extend(
                f"{index}. {option['label']}: {counts.get(option['id'], 0)}"
                for index, option in enumerate(options, 1)
            )
            block_lines.append(f"{t['closed']} · {row['cast_count']} {t['votes']}")
            if row.get("can_archive") is True:
                block_keyboard.append([_button(f"{prefix} · {t['archive']}", f"ps:a:{row['id']}")])
        candidate_lines = lines + block_lines
        candidate_button_count = sum(len(buttons) for buttons in keyboard + block_keyboard)
        has_more = poll_number < len(rows)
        reserved_lines = candidate_lines + (["", t["more"]] if has_more else [])
        if (
            len("\n".join(reserved_lines)) > MAX_MESSAGE_TEXT
            or candidate_button_count > MAX_KEYBOARD_BUTTONS
        ):
            break
        lines = candidate_lines
        keyboard.extend(block_keyboard)
        rendered += 1
    if not rows:
        lines.append(t["empty"])
    elif rendered < len(rows):
        lines.extend(("", t["more"]))
    result = {"text": "\n".join(lines), "link_preview_options": {"is_disabled": True}}
    if keyboard:
        result["reply_markup"] = {"inline_keyboard": keyboard}
    return result


def render_reply(
    state: dict,
    actor_id: str,
    descriptor: dict,
    now: datetime,
    language: str,
) -> dict:
    """Render current authorized poll text only at the final private-send boundary."""
    timestamp(now, "now")
    if not isinstance(descriptor, dict):
        raise DomainError("invalid_field", "descriptor")
    mode = descriptor.get("mode")
    allowed = {
        "private": {"kind", "mode"},
        "list": {"kind", "mode"},
        "review": {"kind", "mode", "review_id"},
        "saved": {"kind", "mode", "action"},
        "cancelled": {"kind", "mode"},
    }
    if descriptor.get("kind") != "polls" or mode not in allowed:
        raise DomainError("invalid_field", "descriptor")
    fields(descriptor, allowed[mode], allowed[mode])
    t = _copy(language)
    if mode == "private":
        return {"text": t["private"], "link_preview_options": {"is_disabled": True}}
    modules = state.get("settings", {}).get("modules", [])
    actor = state.get("members", {}).get(actor_id)
    if not isinstance(modules, list) or "polls" not in modules:
        raise DomainError("module_disabled")
    try:
        actor_revision = strict_revision(actor.get("revision")) if isinstance(actor, dict) else None
    except DomainError:
        actor_revision = None
    if (
        not isinstance(actor, dict)
        or actor.get("id") != actor_id
        or actor.get("active") is not True
        or actor.get("role") == "guest"
        or actor_revision is None
    ):
        raise DomainError("forbidden")
    if mode == "cancelled":
        return {"text": t["cancelled"], "link_preview_options": {"is_disabled": True}}
    if mode == "saved":
        action = descriptor.get("action")
        if action not in {"vote", "close", "archive"}:
            raise DomainError("invalid_field", "action")
        return {
            "text": t[f"saved_{action}"],
            "link_preview_options": {"is_disabled": True},
        }
    projection = poll_domain.view(state, actor, now)
    if mode == "list":
        return _list_reply(projection, language)

    current = poll_reviews.get_current(state, actor_id, descriptor["review_id"], now)
    row = _poll_row(projection, current["poll_id"])
    if row is None:
        raise DomainError("forbidden")
    heading = t[f"review_{current['kind']}"]
    lines = [heading, text(row.get("question"), "question", 240)]
    if current["kind"] == "vote":
        option = next(
            (
                option
                for option in row.get("options", [])
                if option.get("id") == current["option_id"]
            ),
            None,
        )
        if not option:
            raise DomainError("conflict")
        lines.extend((text(option.get("label"), "option", 120), t["not_anonymous"]))
    callback = descriptor["review_id"]
    return {
        "text": "\n".join(lines)[:3800],
        "link_preview_options": {"is_disabled": True},
        "reply_markup": {
            "inline_keyboard": [
                [
                    _button(t["confirm"], f"pr:y:{callback}"),
                    _button(t["cancel"], f"pr:n:{callback}"),
                ]
            ]
        },
    }
