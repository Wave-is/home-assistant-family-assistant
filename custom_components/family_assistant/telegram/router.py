"""Deterministic addressed-message path. LLM is optional, never needed for ping."""

from __future__ import annotations

import re
from datetime import datetime

from ..domain.validation import DomainError
from . import calendar, commands, rewards, routines
from .context import PersonalReply
from .intents import find_member, parse
from .presentation import court_stats, summary

COPY = {
    "en": {
        "alive": "👋 I'm here. Lists, tasks and alarms work without an AI model.",
        "help": (
            "Family Assistant\n/ping — check the bot\n/shopping — shopping list\n"
            "/buy item | quantity | unit\n/bought S000001 | optional purchased quantity\n"
            "/tasks — tasks\n/task "
            "member | task title\n/done T000001 | report\n/approve T000001 — "
            "parent confirmation\n/alarms — wake-up checks\n/stats — scores and "
            "reasons\n/internet member — Kid Control status\n/netpause member\n"
            "/netresume member\n/netgrant member | 30 — temporary access\n"
            "/netschedule member | weekdays | 08:00-22:00\n"
            "Network changes need a reviewed plan and /netconfirm.\n"
            "Reply to a wake-up check using its fresh buttons.\n"
            "/week — this week's scores\n/appeal record ID | reason\n"
            "/award member | points | reason\n/reverse record ID | reason\n"
            "/courtresolve record ID | uphold or reverse | reason"
        ),
        "empty": "No records yet.",
        "saved": "✅ Saved: {id} · {title}",
        "private_saved": (
            "✅ Saved: {id}. Private task details are in your private chat or dashboard."
        ),
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
            "товар | количество | единица\n/bought S000001 | количество (необязательно) — куплено\n"
            "/tasks — "
            "задачи\n/task участник | задача\n/done T000001 | отчёт\n/approve "
            "T000001 — подтверждение родителя\n/alarms — проверки подъёма\n"
            "/stats — баллы и причины\nПодтверждайте подъём свежими кнопками "
            "проверки.\n/internet участник — интернет ребёнка\n/netpause участник\n"
            "/netresume участник\n/netgrant участник | 30 — временный доступ\n"
            "/netschedule участник | будни | 08:00-22:00\n"
            "Сетевые изменения — после проверки плана и /netconfirm.\n"
            "/week — баллы за неделю\n/appeal ID записи | причина\n"
            "/award участник | баллы | причина\n/reverse ID записи | причина\n"
            "/courtresolve ID записи | uphold (оставить) или reverse (отменить) | причина"
        ),
        "empty": "Пока нет записей.",
        "saved": "✅ Сохранено: {id} · {title}",
        "private_saved": (
            "✅ Сохранено: {id}. Подробности личной задачи — в личном чате или на дашборде."
        ),
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
            "товар | кількість | одиниця\n/bought S000001 | кількість (необов’язково) — куплено\n"
            "/tasks — "
            "завдання\n/task учасник | завдання\n/done T000001 | звіт\n/approve "
            "T000001 — підтвердження батьків\n/alarms — перевірки підйому\n"
            "/stats — бали та причини\nПідтверджуйте підйом свіжими кнопками "
            "перевірки.\n/internet учасник — інтернет дитини\n/netpause учасник\n"
            "/netresume учасник\n/netgrant учасник | 30 — тимчасовий доступ\n"
            "/netschedule учасник | будні | 08:00-22:00\n"
            "Мережеві зміни — після перевірки плану та /netconfirm.\n"
            "/week — бали за тиждень\n/appeal ID запису | причина\n"
            "/award учасник | бали | причина\n/reverse ID запису | причина\n"
            "/courtresolve ID запису | uphold (залишити) або reverse (скасувати) | причина"
        ),
        "empty": "Поки немає записів.",
        "saved": "✅ Збережено: {id} · {title}",
        "private_saved": (
            "✅ Збережено: {id}. Подробиці приватного завдання — в особистому чаті або на дашборді."
        ),
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


async def route(
    engine,
    actor: str,
    content: str,
    operation_id: str,
    now: datetime,
    refs=(),
    *,
    fallback=None,
    private=False,
) -> str:
    view = engine.view(actor, now=now)
    from ..domain.task_access import personal_task, private_task

    if not private:
        view["tasks"] = [task for task in view["tasks"] if not private_task(task)]
    language = next(m["language"] for m in view["members"] if m["id"] == actor)
    t = COPY.get(language, COPY["en"])

    def saved(result):
        if "watch_revision" in result and type(result.get("enabled")) is bool:
            from .watch_messages import COMMAND_COPY

            return PersonalReply(
                COMMAND_COPY.get(language, COMMAND_COPY["en"])["on" if result["enabled"] else "off"]
            )

        def scoped(value):
            records = result.get("items", [result])
            return (
                PersonalReply(value)
                if private and any(personal_task(item) for item in records)
                else value
            )

        if not private and private_task(result):
            return t["private_saved"].format(id=result["id"])
        if (
            "template_id" in result
            or "assignees" in result
            and "steps" in result
            or "modes" in result
        ):
            return routines.summary(result, language, private)
        if "participants" in result and "start" in result:
            return t["saved"].format(
                id=result["id"], title=calendar.summary(result, language, private)
            )
        if str(result.get("id", "")).startswith("K") and "mode" in result:
            from .network import render_plan

            return render_plan(result, view, language)
        if result.get("status") in {"learned", "forgotten"}:
            from ..assistant.language import COPY as ASSISTANT_COPY

            return ASSISTANT_COPY[language][result["status"]].format(id=result["id"])
        if "items" in result:
            from ..assistant.language import COPY as ASSISTANT_COPY

            if result.get("status") == "rejected":
                return ASSISTANT_COPY[language]["rejected"]
            return scoped(
                ASSISTANT_COPY[language]["confirmed"].format(
                    result="\n".join(
                        t["private_saved"].format(id=item["id"])
                        if not private and private_task(item)
                        else summary(item, view, language)
                        for item in result["items"]
                    )
                )
            )
        title = (
            rewards.summary(result, language)
            if "cost" in result
            else summary(result, view, language)
        )
        return scoped(t["saved"].format(id=result["id"], title=title))

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
        from .admission import COPY as ADMISSION_COPY
        from .watch_messages import COMMAND_COPY

        return (
            t["help"]
            + rewards.help_text(language)
            + calendar.help_text(language)
            + routines.help_text(language)
            + ADMISSION_COPY.get(language, ADMISSION_COPY["en"])["help"]
            + COMMAND_COPY.get(language, COMMAND_COPY["en"])["help"]
        )
    from .network import parsed as parse_network
    from .network import status as network_status

    network_intent = parse_network(engine.snapshot(), content, now)
    if network_intent:
        if "mikrotik" not in view["settings"]["modules"]:
            raise DomainError("module_disabled")
        action, payload = network_intent
        if action == "read.network_watch_toggle":
            from ..network.watch import public as watch_public
            from .admission import COPY as ADMISSION_COPY

            watch = watch_public(engine.snapshot(), actor)
            if not private:
                return ADMISSION_COPY.get(language, ADMISSION_COPY["en"])["private"]
            enabled = payload["enabled"]
            if (enabled and watch["effective"]) or (not enabled and not watch["enabled"]):
                return saved({"watch_revision": watch["watch_revision"], "enabled": enabled})
            payload = {
                "actor_revision": watch["actor_revision"],
                "watch_revision": watch["watch_revision"],
                "enabled": enabled,
                "min_interval_minutes": watch["min_interval_minutes"],
            }
            if enabled:
                from ..network.admission_inventory import observation_token

                payload["observation_token"] = observation_token(engine.snapshot()["network"], now)
            return saved(
                await commands.execute(
                    engine,
                    actor,
                    content,
                    refs,
                    operation_id,
                    now,
                    "mikrotik.admission_watch_set",
                    payload,
                )
            )
        if action == "read.network_admission":
            from .admission import read as read_admission

            return read_admission(view, now, private=private)
        if action == "read.network":
            return network_status(view, payload.get("member"), language)
        return saved(
            await commands.execute(engine, actor, content, refs, operation_id, now, action, payload)
        )
    from ..domain.learning import resolve

    original_content = content
    command, _, tail = content.partition(" ")
    command = command.casefold()
    parse_error = None
    try:
        intent = (
            parse(engine.snapshot(), view, content, now, refs)
            if not command.startswith("/")
            else None
        )
    except DomainError as err:
        parse_error, intent = err, None
    if intent is None and not command.startswith("/"):
        canonical = resolve(engine.snapshot(), actor, content)
        if canonical != content:
            content = canonical
            command, _, tail = content.partition(" ")
            command = command.casefold()
            parse_error = None
            try:
                intent = (
                    parse(engine.snapshot(), view, content, now, refs)
                    if not command.startswith("/")
                    else None
                )
            except DomainError as err:
                parse_error = err
    if parse_error:
        if fallback is not None and parse_error.code in {
            "ambiguous_command",
            "ambiguous_member",
            "context_required",
            "invalid_deadline",
        }:
            return await fallback(actor, original_content, operation_id, now, refs)
        raise parse_error
    if intent and intent.action.startswith("read."):
        command = {"read.court": "/stats", "read.tasks": "/tasks"}[intent.action]
    if command in {"/shopping", "/tasks", "/stats", "/week", "/alarms"}:
        bucket = {
            "/shopping": "shopping",
            "/tasks": "tasks",
            "/stats": "court",
            "/week": "court",
            "/alarms": "alarms",
        }[command]
        if bucket not in view["settings"]["modules"]:
            raise DomainError("module_disabled")
        if bucket == "court":
            return court_stats(engine.view(actor, now=now), language, weekly=command == "/week")
        lines = []
        for item in view[bucket]:
            if item.get("status") in {"archived", "cancelled", "rejected", "merged"}:
                continue
            if bucket == "shopping" and item.get("status") == "purchased":
                continue
            label = summary(item, view, language)
            lines.append(f"{item['id']} · {label}")
        response = "\n".join(lines)[:3800] or t["empty"]
        if private and bucket == "tasks" and any(personal_task(item) for item in view[bucket]):
            return PersonalReply(response)
        return response
    if command in {"/rewards", "/wallet"}:
        return rewards.read(view, language, only_wallet=command == "/wallet")
    if command == "/calendar":
        return calendar.read(view, language, private)
    if command == "/routines":
        return routines.read(view, language, private)
    fields = [part.strip() for part in tail.split("|")]
    routine_intent = routines.parsed(engine.snapshot(), view, command, fields, private)
    if routine_intent:
        return saved(
            await commands.execute(engine, actor, content, refs, operation_id, now, *routine_intent)
        )
    calendar_intent = calendar.parsed(view, command, fields)
    if calendar_intent:
        return saved(
            await commands.execute(
                engine, actor, content, refs, operation_id, now, *calendar_intent
            )
        )
    reward_intent = rewards.parsed(view, command, fields)
    if reward_intent:
        return saved(
            await commands.execute(engine, actor, content, refs, operation_id, now, *reward_intent)
        )
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
    elif command == "/bought" and len(fields) in {1, 2}:
        action, payload = "shopping.purchase", {"id": fields[0]}
        if len(fields) == 2:
            try:
                payload["quantity"] = float(fields[1].replace(",", "."))
            except ValueError:
                raise DomainError("invalid_field", "quantity") from None
    elif command == "/task" and len(fields) == 2:
        action, payload = (
            "tasks.create",
            {"assignee": member_by_name(engine.snapshot(), fields[0]), "title": fields[1]},
        )
    elif command == "/done" and len(fields) == 2:
        action, payload = "tasks.submit", {"id": fields[0], "report": fields[1]}
    elif command == "/approve" and len(fields) == 1:
        action, payload = "tasks.complete", {"id": fields[0]}
    elif command in {"/appeal", "/reverse"} and len(fields) == 2:
        record = next((r for r in view["court"] if r["id"] == fields[0]), None)
        if not record:
            raise DomainError("not_found")
        action, payload = (
            "court." + command[1:],
            {"id": record["id"], "revision": record["revision"], "reason": fields[1]},
        )
    elif command == "/courtresolve" and len(fields) == 3:
        record = next((r for r in view["court"] if r["id"] == fields[0]), None)
        if not record:
            raise DomainError("not_found")
        action, payload = (
            "court.resolve_appeal",
            {
                "id": record["id"],
                "revision": record["revision"],
                "decision": fields[1],
                "reason": fields[2],
            },
        )
    elif command == "/award" and len(fields) == 3:
        if not re.fullmatch(r"[+-]?\d{1,3}", fields[1]):
            raise DomainError("invalid_field", "points")
        action, payload = (
            "court.award",
            {
                "member": member_by_name(engine.snapshot(), fields[0]),
                "points": int(fields[1]),
                "reason": fields[2],
            },
        )
    elif command in {"/confirm", "/cancel"} and len(fields) == 1:
        action, payload = (
            "conversation." + ("confirm" if command == "/confirm" else "reject"),
            {"id": fields[0]},
        )
    elif command == "/learn" and len(fields) == 2:
        action, payload = "conversation.learn", {"source": fields[0], "canonical": fields[1]}
    elif command == "/forget" and len(fields) == 1:
        action, payload = "conversation.forget", {"id": fields[0]}
    if action is None:
        if fallback is not None and not command.startswith("/"):
            return await fallback(actor, original_content, operation_id, now, refs)
        return t["unknown"]
    result = await commands.execute(
        engine, actor, original_content, refs, operation_id, now, action, payload
    )
    return saved(result)
