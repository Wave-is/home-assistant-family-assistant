"""Deterministic addressed-message path. LLM is optional, never needed for ping."""

from __future__ import annotations

import re
from datetime import datetime

from ..domain.validation import DomainError
from . import commands
from .intents import find_member, parse
from .presentation import summary

COPY = {
    "en": {
        "alive": "👋 I'm here. Lists, tasks and alarms work without an AI model.",
        "help": (
            "Family Assistant\n/ping — check the bot\n/shopping — shopping list\n"
            "/buy item | quantity | unit\n/bought S000001\n/tasks — tasks\n/task "
            "member | task title\n/done T000001 | report\n/approve T000001 — "
            "parent confirmation\n/alarms — wake-up checks\n/stats — scores and "
            "reasons\nReply to a wake-up check using its fresh buttons."
        ),
        "empty": "No records yet.",
        "saved": "✅ Saved: {id} · {title}",
        "unknown": (
            "I haven't understood the action yet. Nothing was changed. Use "
            "/help for supported commands."
        ),
        "error": "Could not complete the action: {error}. Nothing was changed.",
        "accepted": "✅ Correct! {stage}",
        "wrong": "🧩 Not quite. Try the current question again.",
        "waiting_second": "I'll send a fresh check in a few minutes.",
        "complete": "Wake-up confirmed.",
    },
    "ru": {
        "alive": "👋 Я тут. Списки, задачи и будильники работают без языковой модели.",
        "help": (
            "Family Assistant\n/ping — проверить бота\n/shopping — покупки\n/buy "
            "товар | количество | единица\n/bought S000001 — куплено\n/tasks — "
            "задачи\n/task участник | задача\n/done T000001 | отчёт\n/approve "
            "T000001 — подтверждение родителя\n/alarms — проверки подъёма\n"
            "/stats — баллы и причины\nПодтверждайте подъём свежими кнопками "
            "проверки."
        ),
        "empty": "Пока нет записей.",
        "saved": "✅ Сохранено: {id} · {title}",
        "unknown": (
            "Пока не понял действие. Ничего не изменено. В /help есть поддерживаемые команды."
        ),
        "error": "Не удалось выполнить действие: {error}. Ничего не изменено.",
        "accepted": "✅ Верно! {stage}",
        "wrong": "🧩 Не совсем. Попробуйте решить текущую задачу ещё раз.",
        "waiting_second": "Через несколько минут пришлю новую проверку.",
        "complete": "Подъём подтверждён.",
    },
    "uk": {
        "alive": "👋 Я тут. Списки, завдання та будильники працюють без мовної моделі.",
        "help": (
            "Family Assistant\n/ping — перевірити бота\n/shopping — покупки\n/buy "
            "товар | кількість | одиниця\n/bought S000001 — куплено\n/tasks — "
            "завдання\n/task учасник | завдання\n/done T000001 | звіт\n/approve "
            "T000001 — підтвердження батьків\n/alarms — перевірки підйому\n"
            "/stats — бали та причини\nПідтверджуйте підйом свіжими кнопками "
            "перевірки."
        ),
        "empty": "Поки немає записів.",
        "saved": "✅ Збережено: {id} · {title}",
        "unknown": ("Поки не зрозумів дію. Нічого не змінено. У /help є підтримувані команди."),
        "error": "Не вдалося виконати дію: {error}. Нічого не змінено.",
        "accepted": "✅ Правильно! {stage}",
        "wrong": "🧩 Не зовсім. Спробуйте розв’язати поточну задачу ще раз.",
        "waiting_second": "За кілька хвилин надішлю нову перевірку.",
        "complete": "Підйом підтверджено.",
    },
}


def addressed(message: dict, bot: dict) -> str | None:
    if (
        message.get("sender_chat")
        or message.get("from", {}).get("is_bot")
        or message.get("forward_origin")
    ):
        return None
    content = message.get("text", "")
    if not isinstance(content, str) or not content.strip() or len(content) > 4096:
        return None
    username = re.escape(bot["username"])
    mention = re.compile(rf"(?<!\w)@{username}(?!\w)", re.I)
    command = re.match(r"^/\w+(?:@([\w]+))?", content)
    if command and command.group(1) and command.group(1).casefold() != bot["username"].casefold():
        return None
    direct = message.get("chat", {}).get("type") == "private"
    reply = message.get("reply_to_message", {}).get("from", {}).get("id") == bot["id"]
    if not (direct or command or reply or mention.search(content)):
        return None
    content = re.sub(rf"(^/\w+)@{username}(?!\w)", r"\1", content, flags=re.I)
    return mention.sub("", content).strip()


def member_by_name(state: dict, value: str) -> str:
    return find_member(state, value)


async def route(engine, actor: str, content: str, operation_id: str, now: datetime, refs=()) -> str:
    view = engine.view(actor)
    language = next(m["language"] for m in view["members"] if m["id"] == actor)
    t = COPY.get(language, COPY["en"])

    def saved(result):
        return t["saved"].format(id=result["id"], title=summary(result, view, language))

    prior = commands.previous(engine, actor, content, refs, operation_id)
    if prior:
        return saved(
            await engine.execute(actor, prior["action"], prior["payload"], operation_id, now)
        )
    normalized = content.casefold().strip(" .?!🙂")
    if normalized in {
        "/ping",
        "тут",
        "жив",
        "живой",
        "живий",
        "ты тут",
        "ти тут",
        "here",
        "alive",
        "ping",
    }:
        return t["alive"]
    if normalized in {"/start", "/help", "help", "помощь", "допомога"}:
        return t["help"]
    command, _, tail = content.partition(" ")
    command = command.casefold()
    intent = (
        parse(engine.snapshot(), view, content, now, refs) if not command.startswith("/") else None
    )
    if intent and intent.action.startswith("read."):
        command = {"read.court": "/stats", "read.tasks": "/tasks"}[intent.action]
    if command in {"/shopping", "/tasks", "/stats", "/alarms"}:
        bucket = {
            "/shopping": "shopping",
            "/tasks": "tasks",
            "/stats": "court",
            "/alarms": "alarms",
        }[command]
        if bucket not in view["settings"]["modules"]:
            raise DomainError("module_disabled")
        lines = []
        for item in view[bucket]:
            if item.get("status") in {"archived", "cancelled", "rejected"}:
                continue
            label = summary(item, view, language)
            lines.append(f"{item['id']} · {label}")
        return "\n".join(lines)[:3800] or t["empty"]
    fields = [part.strip() for part in tail.split("|")]
    action, payload = (intent.action, intent.payload) if intent else (None, None)
    if command == "/buy" and 1 <= len(fields) <= 3:
        try:
            quantity = float(fields[1].replace(",", ".")) if len(fields) > 1 else 1
        except ValueError:
            raise DomainError("invalid_field", "quantity") from None
        action, payload = (
            "shopping.add",
            {"name": fields[0], "quantity": quantity, "unit": fields[2] if len(fields) > 2 else ""},
        )
    elif command == "/bought" and len(fields) == 1:
        action, payload = "shopping.purchase", {"id": fields[0]}
    elif command == "/task" and len(fields) == 2:
        action, payload = (
            "tasks.create",
            {"assignee": member_by_name(engine.snapshot(), fields[0]), "title": fields[1]},
        )
    elif command == "/done" and len(fields) == 2:
        action, payload = "tasks.submit", {"id": fields[0], "report": fields[1]}
    elif command == "/approve" and len(fields) == 1:
        action, payload = "tasks.complete", {"id": fields[0]}
    if action is None:
        return t["unknown"]
    result = await commands.execute(
        engine, actor, content, refs, operation_id, now, action, payload
    )
    return saved(result)
