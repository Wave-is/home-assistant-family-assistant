"""Deterministic addressed-message path. LLM is optional, never needed for ping."""

from __future__ import annotations

import re
from datetime import datetime

from ..domain.validation import DomainError
from . import alarm_commands, calendar, commands, rewards, routines, task_commands
from .context import PersonalReply
from .intents import find_member, layout_trans, normalize, parse
from .presentation import court_stats, summary

COPY = {
    "en": {
        "alive": "👋 I'm here. Lists, tasks and alarms work without an AI model.",
        "help": (
            "Family Assistant\n/ping — check the bot\n/shopping — shopping list\n"
            "/buy item | quantity | unit\n/bought S000001 | optional purchased quantity\n"
            "/tasks — tasks\n/task "
            "member | task title\n/done T000001 | report\n"
            "/report T000001 — photo caption, no note\n"
            "/approve T000001 — "
            "parent confirmation\n/alarms — wake-up checks\n/stats — scores and "
            "reasons\n/internet member — Kid Control status\n/netpause member\n"
            "/netresume member\n/netgrant member | 30 — temporary access\n"
            "/netschedule member | weekdays | 08:00-22:00\n"
            "Network changes need a reviewed plan and /netconfirm.\n"
            "Reply to a wake-up check using its fresh buttons.\n"
            "/week — this week's scores\n/appeal record ID | reason\n"
            "/award member | points | reason\n/reverse record ID | reason\n"
            "/courtresolve record ID | uphold or reverse | reason\n"
            "/watchlist — price watch\n/watch URL | optional name\n"
            "/unwatch ID — remove price watch"
        ),
        "empty": "No records yet.",
        "saved": "✅ Saved: {id} · {title}",
        "unwatched": "🗑 Price watch removed: {id} · {title}",
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
            "задачи\n/task участник | задача\n/done T000001 | отчёт\n"
            "/report T000001 — подпись к фото, без примечания\n/approve "
            "T000001 — подтверждение родителя\n/alarms — проверки подъёма\n"
            "/stats — баллы и причины\nПодтверждайте подъём свежими кнопками "
            "проверки.\n/internet участник — интернет ребёнка\n/netpause участник\n"
            "/netresume участник\n/netgrant участник | 30 — временный доступ\n"
            "/netschedule участник | будни | 08:00-22:00\n"
            "Сетевые изменения — после проверки плана и /netconfirm.\n"
            "/week — баллы за неделю\n/appeal ID записи | причина\n"
            "/award участник | баллы | причина\n/reverse ID записи | причина\n"
            "/courtresolve ID записи | uphold (оставить) или reverse (отменить) | причина\n"
            "/watchlist — мониторинг цен\n/watch ссылка | название (необязательно)\n"
            "/unwatch ID — удалить из отслеживания"
        ),
        "empty": "Пока нет записей.",
        "saved": "✅ Сохранено: {id} · {title}",
        "unwatched": "🗑 Отслеживание снято: {id} · {title}",
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
            "завдання\n/task учасник | завдання\n/done T000001 | звіт\n"
            "/report T000001 — підпис до фото, без примітки\n/approve "
            "T000001 — підтвердження батьків\n/alarms — перевірки підйому\n"
            "/stats — бали та причини\nПідтверджуйте підйом свіжими кнопками "
            "перевірки.\n/internet участник — інтернет дитини\n/netpause учасник\n"
            "/netresume учасник\n/netgrant учасник | 30 — тимчасовий доступ\n"
            "/netschedule учасник | будні | 08:00-22:00\n"
            "Мережеві зміни — після перевірки плану та /netconfirm.\n"
            "/week — бали за тиждень\n/appeal ID запису | причина\n"
            "/award учасник | бали | причина\n/reverse ID запису | причина\n"
            "/courtresolve ID запису | uphold (залишити) або reverse (скасувати) | причина\n"
            "/watchlist — моніторинг цін\n/watch посилання | назва (необов’язково)\n"
            "/unwatch ID — видалити з відстеження"
        ),
        "empty": "Поки немає записів.",
        "saved": "✅ Збережено: {id} · {title}",
        "unwatched": "🗑 Відстеження скасовано: {id} · {title}",
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


def image_file_id(message: dict) -> str | None:
    """Select a bounded Telegram image reference; never download while polling."""
    for source in (message, message.get("reply_to_message")):
        if not isinstance(source, dict):
            continue
        photos = source.get("photo")
        if isinstance(photos, list) and photos:
            selected = photos[-1]
        else:
            selected = source.get("document")
            if not isinstance(selected, dict) or not str(selected.get("mime_type", "")).startswith(
                "image/"
            ):
                continue
        if not isinstance(selected, dict):
            raise DomainError("photo_unavailable")
        file_id = selected.get("file_id")
        size = selected.get("file_size")
        if size is not None and (type(size) is not int or size < 0):
            raise DomainError("photo_unavailable")
        if size is not None and size > 6_000_000:
            raise DomainError("file_too_large")
        if not isinstance(file_id, str) or not file_id.strip() or len(file_id) > 512:
            raise DomainError("photo_unavailable")
        return file_id.strip()
    return None


def addressed(message: dict, bot: dict, *, language: str = "ru") -> str | None:
    if (
        message.get("sender_chat")
        or message.get("from", {}).get("is_bot")
        or message.get("forward_origin")
    ):
        return None
    raw_content = message.get("text") or message.get("caption") or ""
    if not isinstance(raw_content, str) or len(raw_content) > 4096:
        return None
    has_photo = bool(
        message.get("photo")
        or (
            isinstance(message.get("document"), dict)
            and str(message.get("document", {}).get("mime_type", "")).startswith("image/")
        )
    )
    replied_msg = message.get("reply_to_message") or {}
    reply_has_photo = bool(
        replied_msg.get("photo")
        or (
            isinstance(replied_msg.get("document"), dict)
            and str(replied_msg.get("document", {}).get("mime_type", "")).startswith("image/")
        )
    )
    photo_prompt = {
        "en": "Describe what is shown in the photo.",
        "ru": "Опиши, что изображено на фото.",
        "uk": "Опиши, що зображено на фото.",
    }.get(language, "Describe what is shown in the photo.")
    content = raw_content.strip()
    if not content and (has_photo or reply_has_photo):
        content = photo_prompt
    if not content:
        return None
    username = re.escape(bot["username"])
    mention = re.compile(rf"(?<!\w)@{username}(?!\w)", re.I)
    command = re.match(r"^/\w+(?:@([\w]+))?", content)
    if command and command.group(1) and command.group(1).casefold() != bot["username"].casefold():
        return None
    direct = message.get("chat", {}).get("type") == "private"
    reply = replied_msg.get("from", {}).get("id") == bot["id"]
    if not (direct or command or reply or mention.search(content)):
        return None
    content = re.sub(rf"(^/\w+)@{username}(?!\w)", r"\1", content, flags=re.I)
    cleaned = mention.sub("", content).strip()
    if not cleaned and (has_photo or reply_has_photo):
        cleaned = photo_prompt
    return cleaned or None


COMMAND_ALIASES = {
    "/commands": "/help",
    "/команды": "/help",
    "/команди": "/help",
    "/помощник": "/help",
    "/помічник": "/help",
    "/мои": "/mine",
    "/мої": "/mine",
    "/архив": "/archive",
    "/архів": "/archive",
    "/изменитьзадачу": "/edit",
    "/одобритьпокупку": "/approvebuy",
    "/отклонитьпокупку": "/rejectbuy",
    "/переделать": "/changes",
    "/доопрацювати": "/changes",
    "/отменитьзадачу": "/canceltask",
    "/скасуватизавдання": "/canceltask",
    "/начать": "/begin",
    "/почати": "/begin",
    "/спросить": "/ask",
    "/запитати": "/ask",
    # Tasks
    "/дела": "/tasks",
    "/задачи": "/tasks",
    "/таски": "/tasks",
    "/завдання": "/tasks",
    "/справи": "/tasks",
    "/todo": "/tasks",
    # Shopping
    "/покупки": "/shopping",
    "/шопинг": "/shopping",
    "/шоппинг": "/shopping",
    "/шопінг": "/shopping",
    "/список": "/shopping",
    # Court / Stats
    "/статистика": "/stats",
    "/стата": "/stats",
    "/суд": "/stats",
    "/баллы": "/stats",
    "/бали": "/stats",
    "/штрафы": "/stats",
    "/штрафи": "/stats",
    "/очки": "/stats",
    "/рейтинг": "/stats",
    # Week
    "/неделя": "/week",
    "/тиждень": "/week",
    # Alarms
    "/будильники": "/alarms",
    "/будильник": "/alarms",
    "/подъем": "/alarms",
    "/підйом": "/alarms",
    # Calendar
    "/календарь": "/calendar",
    "/календар": "/calendar",
    "/планы": "/calendar",
    "/плани": "/calendar",
    "/розклад": "/calendar",
    # Routines
    "/рутины": "/routines",
    "/рутини": "/routines",
    "/привычки": "/routines",
    "/звички": "/routines",
    # Rewards & Wallet
    "/награды": "/rewards",
    "/нагороди": "/rewards",
    "/магазин": "/rewards",
    "/кошелек": "/wallet",
    "/кошелёк": "/wallet",
    "/гаманець": "/wallet",
    "/баланс": "/wallet",
    # Watchlist / Prices
    "/цены": "/prices",
    "/ціни": "/prices",
    "/вишлист": "/prices",
    "/вішліст": "/prices",
    # Help & Ping
    "/помощь": "/help",
    "/допомога": "/help",
    "/хелп": "/help",
    "/старт": "/help",
    "/пинг": "/ping",
    "/пінг": "/ping",
    # Actions
    "/купи": "/buy",
    "/купить": "/buy",
    "/придбай": "/buy",
    "/придбати": "/buy",
    "/куплено": "/bought",
    "/купил": "/bought",
    "/купила": "/bought",
    "/купили": "/bought",
    "/придбано": "/bought",
    "/придбав": "/bought",
    "/придбала": "/bought",
    "/задача": "/task",
    "/створити_завдання": "/task",
    "/таск": "/task",
    "/сдано": "/done",
    "/сдал": "/done",
    "/сдала": "/done",
    "/здано": "/done",
    "/здав": "/done",
    "/здала": "/done",
    "/готово": "/done",
    "/принято": "/approve",
    "/принять": "/accept",
    "/одобрить": "/approve",
    "/схвалити": "/approve",
    "/прийняти": "/accept",
    "/схвалено": "/approve",
    "/штраф": "/award",
    "/бонус": "/award",
    "/наградить": "/award",
    "/нагородити": "/award",
    "/апелляция": "/appeal",
    "/апеляція": "/appeal",
    "/отмена": "/cancel",
    "/скасувати": "/cancel",
    "/скасування": "/cancel",
    "/подтвердить": "/confirm",
    "/підтвердити": "/confirm",
}


def canonical_command(cmd: str) -> str:
    c = cmd.casefold()
    if c.startswith("/."):
        c = "/" + c[2:]
    if c in COMMAND_ALIASES:
        return COMMAND_ALIASES[c]
    if c.startswith("/") and not re.search(r"[а-яіїєґ]", c, re.I):
        trans_cmd = "/" + normalize(layout_trans(c[1:]))
        if trans_cmd in COMMAND_ALIASES:
            return COMMAND_ALIASES[trans_cmd]
    return c


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

    from ..online_school.messages import query as school_query

    school_reply = school_query(engine, actor, content, now, private=private, language=language)
    if school_reply is not None:
        return school_reply

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
                key = "feedback_saved" if result.get("feedback_id") else "rejected"
                return ASSISTANT_COPY[language][key]
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
    head, _, tail = content.partition(" ")
    normalized = normalize(canonical_command(head) if not tail else content)
    if normalized in {
        "/ping",
        "ping",
        "пинг",
        "пінг",
        "тут",
        "жив",
        "живой",
        "живий",
        "ты тут",
        "ти тут",
        "here",
        "alive",
        "status",
        "healthcheck",
        "на связи",
        "на зв'язку",
        "ты на связи",
        "ти на зв'язку",
        "работаешь",
        "работает",
        "працюєш",
        "працює",
        "бот ты тут",
        "бот ти тут",
        "ты жив",
        "ты живой",
        "ти живий",
        "отзовись",
        "відгукнись",
        "ау",
        "ты где",
        "де ти",
        "u there",
        "are you there",
        "are you alive",
    } or (
        not re.search(r"[а-яіїєґ]", normalized, re.I)
        and normalize(layout_trans(normalized))
        in {"пинг", "тут", "ты тут", "ти тут", "жив", "живой", "живий", "на связи"}
    ):
        return t["alive"]
    if normalized in {
        "/start",
        "/help",
        "help",
        "start",
        "помощь",
        "допомога",
        "хелп",
        "помоги",
        "что ты умеешь",
        "що ти вмієш",
        "команды",
        "команди",
        "список команд",
        "как пользоваться",
        "як користуватися",
        "инструкция",
        "інструкція",
        "справка",
        "довідка",
        "меню",
        "/меню",
        "/справка",
        "/інструкція",
        "/довідка",
        "/помощь",
        "/допомога",
    } or (
        not re.search(r"[а-яіїєґ]", normalized, re.I)
        and normalize(layout_trans(normalized))
        in {"помощь", "допомога", "хелп", "команды", "команди", "меню"}
    ):
        from .admission import COPY as ADMISSION_COPY
        from .watch_messages import COMMAND_COPY

        return (
            t["help"]
            + rewards.help_text(language)
            + calendar.help_text(language)
            + routines.help_text(language)
            + ADMISSION_COPY.get(language, ADMISSION_COPY["en"])["help"]
            + COMMAND_COPY.get(language, COMMAND_COPY["en"])["help"]
            + task_commands.help_text(language)
        )
    from .proposal_reply import parse_reply

    proposal_reply = parse_reply(content, refs)
    if proposal_reply is not None:
        action, payload = proposal_reply
        return saved(
            await commands.execute(engine, actor, content, refs, operation_id, now, action, payload)
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
    if "court" in view.get("settings", {}).get("modules", []):
        from ..court import parse_message
        from .court_router import route_court

        court_parsed = parse_message(content, members=engine.snapshot()["members"].values())
        if court_parsed.action != "ignore":
            court_reply = await route_court(
                engine, actor, content, operation_id, now, court_parsed, view, language, refs=refs
            )
            if court_reply is not None:
                return court_reply

    from ..domain.learning import resolve

    original_content = content
    command, _, tail = content.partition(" ")
    command = canonical_command(command)
    if command == "/ask":
        if fallback is not None and tail.strip():
            return await fallback(actor, tail.strip(), operation_id, now, refs)
        return t["unknown"]
    if command == "/alarm" and not tail.strip():
        command = "/alarms"
    alarm_intent = alarm_commands.parsed(engine.snapshot(), view, original_content)
    if alarm_intent:
        if len(alarm_intent) == 1:
            operation = alarm_intent[0]
            action, payload = operation["action"], operation["payload"]
        else:
            action, payload = "batch", {"commands": alarm_intent}
        return saved(
            await commands.execute(
                engine, actor, original_content, refs, operation_id, now, action, payload
            )
        )
    if original_content.partition(" ")[0].casefold() == "/завдання" and tail.strip():
        command = "/task"
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
            command = canonical_command(command)
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
        command = {
            "read.court": "/stats",
            "read.tasks": "/tasks",
            "read.mine": "/mine",
            "read.shopping": "/shopping",
            "read.alarms": "/alarms",
            "read.calendar": "/calendar",
            "read.routines": "/routines",
            "read.watchlist": "/prices",
            "read.rewards": "/rewards",
            "read.wallet": "/wallet",
        }[intent.action]
    if command in {
        "/shopping",
        "/tasks",
        "/mine",
        "/stats",
        "/week",
        "/alarms",
        "/watchlist",
        "/prices",
    }:
        bucket = {
            "/shopping": "shopping",
            "/tasks": "tasks",
            "/mine": "tasks",
            "/stats": "court",
            "/week": "court",
            "/alarms": "alarms",
            "/watchlist": "price_watches",
            "/prices": "price_watches",
        }[command]
        module = "price_watch" if bucket == "price_watches" else bucket
        if module not in view["settings"]["modules"]:
            raise DomainError("module_disabled")
        if bucket == "court":
            return court_stats(engine.view(actor, now=now), language, weekly=command == "/week")
        lines = []
        for item in view.get(bucket, []):
            if command == "/mine" and item.get("assignee") != actor:
                continue
            if item.get("status") in {"archived", "cancelled", "rejected", "merged"}:
                continue
            if bucket == "tasks" and item.get("status") == "completed":
                continue
            if bucket == "shopping" and item.get("status") == "purchased":
                continue
            label = summary(item, view, language)
            lines.append(f"{item['id']} · {label}")
            if bucket == "price_watches" and item.get("url"):
                lines.append(f"  {item['url']}")
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
    task_intent = task_commands.parsed(engine.snapshot(), view, command, tail, now, refs)
    if task_intent:
        return saved(
            await commands.execute(
                engine, actor, original_content, refs, operation_id, now, *task_intent
            )
        )
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
        if len(fields) == 1 and (match := re.fullmatch(r"(S\d{6,})\s+(.+)", fields[0], re.I)):
            fields = [match[1], match[2]]
        action, payload = (
            "shopping.purchase",
            {"id": task_commands.shopping_target(view, fields[0])},
        )
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
    elif command == "/done" and len(fields) in {1, 2}:
        if len(fields) == 1 and (match := re.fullmatch(r"(T\d{6,})(?:\s+(.+))?", fields[0], re.I)):
            fields = [match[1], match[2] or ""]
        if len(fields) != 2:
            raise DomainError("context_required")
        action, payload = "tasks.submit", {"id": fields[0].upper(), "report": fields[1]}
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
            ("tasks.complete", {"id": fields[0].upper()})
            if command == "/confirm" and re.fullmatch(r"T\d{6,}", fields[0], re.I)
            else (
                "conversation." + ("confirm" if command == "/confirm" else "reject"),
                {"id": fields[0]},
            )
        )
    elif command == "/feedback" and len(fields) == 3:
        from ..assistant.language import COPY as ASSISTANT_COPY

        if not private:
            return ASSISTANT_COPY[language]["feedback_private"]
        action, payload = (
            "conversation.reject",
            {
                "id": fields[0],
                "feedback": {"category": fields[1], "expected": fields[2]},
            },
        )
    elif command == "/learn" and len(fields) == 2:
        action, payload = "conversation.learn", {"source": fields[0], "canonical": fields[1]}
    elif command == "/forget" and len(fields) == 1:
        action, payload = "conversation.forget", {"id": fields[0]}
    elif (
        (command == "/watch" and 1 <= len(fields) <= 2)
        or command.startswith("http://")
        or command.startswith("https://")
    ):
        if command == "/watch":
            url = fields[0]
            name = fields[1] if len(fields) == 2 and fields[1] else None
        else:
            url = original_content.split("|")[0].strip()
            name_parts = original_content.split("|", 1)
            name = name_parts[1].strip() if len(name_parts) > 1 and name_parts[1].strip() else None
        action, payload = "price_watch.add", {"url": url}
        if name:
            payload["name"] = name
    elif command == "/unwatch" and len(fields) == 1:
        target_id = fields[0].strip().upper()
        watches = view.get("price_watches", [])
        record = next((r for r in watches if r["id"].upper() == target_id), None)
        if not record:
            raise DomainError("not_found")
        action, payload = (
            "price_watch.remove",
            {"id": record["id"], "revision": record["revision"]},
        )
    if action is None:
        if fallback is not None and not command.startswith("/"):
            return await fallback(actor, original_content, operation_id, now, refs)
        return t["unknown"]
    if action == "conversation.reject" and "feedback" in payload:
        # These exact ID-bound fields need no separate interpretation plan.
        # Persist the note and rejection once, without another raw-text copy in
        # Telegram's plan cache (the channel's own message history is separate).
        return saved(await engine.execute(actor, action, payload, operation_id, now))
    result = await commands.execute(
        engine, actor, original_content, refs, operation_id, now, action, payload
    )
    if action == "price_watch.remove":
        return t.get("unwatched", t["saved"]).format(
            id=result["id"], title=result.get("name", result["id"])
        )
    return saved(result)
