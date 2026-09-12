"""Localized notification envelopes; no parse_mode for user-supplied text."""

from ..domain.validation import DomainError, timestamp
from ..notifications import DeliveryError

MAX_SCHOOL_MATERIALS = 20

MESSAGES = {
    "en": {
        "routine_step": "🪜 {title} · Step {step_number}: {step_title}",
        "routine_overdue": (
            "🪜 {member} · {title}: still waiting for {step_title}. No automatic penalty."
        ),
        "routine_closed": "✅ {member} · {title}: {step_title} — {outcome}.",
        "routine_completed": "✅ Routine completed: {title}",
        "calendar_reminder": "📅 {title} · {start}\n{location}\n{preparation}",
        "reward_requested": (
            "🎁 {member} requests {id} · {title}. Reserved: {cost} points. "
            "Parent review is required."
        ),
        "reward_changed": "🎁 {id} · {title}: {status}. Reason: {reason}",
        "reward_expired": "🎁 {id} · {title}: request expired; its reserved points are released.",
        "network_plan_finished": (
            "🌐 Network plan {id}: {status}. Details and read-back are on the Home network card."
        ),
        "network_watch_cleared": (
            "✅ All previously unreviewed devices have been reviewed. "
            "The network discovery alert is closed. Review the Home network card."
        ),
        "alarm_challenge": "⏰ Wake-up check: {question} = ?\nChoose the answer below.",
        "alarm_missed": "⏰ {member}: wake-up was not confirmed within 30 minutes.",
        "alarm_closed": "✅ {member}: the wake-up incident is closed ({stage}).",
        "alarm_device_error": "⚠️ The wake-up siren needs attention. Check Family Assistant in HA.",
        "alarm_device_recovered": "✅ The wake-up siren is responding again.",
        "task_assigned": "📋 New task: {id} · {title}",
        "task_review": "📸 Review requested: {id} · {title}",
        "task_reminder": "📋 Task due soon: {id} · {title} · {due_at}",
        "task_personal_due": "🔒 Personal reminder: {id} · {title} · {due_at}",
        "task_overdue": "⚠️ {member}: task overdue: {id} · {title}. Parent review is needed.",
        "task_incident_closed": (
            "✅ The overdue incident for {member}'s task {id} is closed. "
            "Any recorded points remain separately reviewable."
        ),
        "shopping_approval": "🛒 Purchase approval requested: {id} · {title}",
        "price_watch_drop": (
            "📉 Price drop: {name} — {old_price} → {new_price} {currency}. Check the link."
        ),
        "price_watch_available": ("✅ Back in stock: {name} — {price_text}. Check the link."),
        "pantry_expiry": (
            "📦 Pantry reminder: {name} has the recorded expiry date {expires_on}. "
            "Check it manually. This is not a food-safety assessment, and stock was not changed."
        ),
        "school_preparation_reminder": (
            "🎒 School preparation for {member} on {date} · {timetable}. "
            "Pinned routine: {routine}. Materials: {materials}. "
            "Review them and start the routine yourself; nothing was started automatically."
        ),
        "court_appeal": "⚖️ An appeal needs a parent's review: {id}",
        "court_appeal_resolved": "⚖️ Appeal {id}: {decision}. The reason is in the court card.",
        "court_weekly": (
            "⚖️ Weekly results: {period}\n{summary}\n\nBalances were not reset. "
            "This report records the result at publication; later corrections remain in the ledger."
        ),
    },
    "ru": {
        "routine_step": "🪜 {title} · Шаг {step_number}: {step_title}",
        "routine_overdue": (
            "🪜 {member} · {title}: ещё ждём шаг «{step_title}». Автоматического штрафа нет."
        ),
        "routine_closed": "✅ {member} · {title}: {step_title} — {outcome}.",
        "routine_completed": "✅ Рутина завершена: {title}",
        "calendar_reminder": "📅 {title} · {start}\n{location}\n{preparation}",
        "reward_requested": (
            "🎁 {member}: заявка {id} · {title}. Резерв: {cost} баллов. Нужна проверка родителя."
        ),
        "reward_changed": "🎁 {id} · {title}: {status}. Причина: {reason}",
        "reward_expired": "🎁 {id} · {title}: срок заявки истёк, её резерв баллов освобождён.",
        "network_plan_finished": (
            "🌐 План сети {id}: {status}. "
            "Подробности и результат проверки — в карточке домашней сети."
        ),
        "network_watch_cleared": (
            "✅ Все ранее неизвестные устройства проверены. "
            "Оповещение о новых устройствах в сети закрыто. Откройте карточку домашней сети."
        ),
        "alarm_challenge": "⏰ Проверка подъёма: {question} = ?\nВыберите ответ кнопкой.",
        "alarm_missed": "⏰ {member}: подъём не подтверждён за 30 минут.",
        "alarm_closed": "✅ {member}: проверка подъёма закрыта ({stage}).",
        "alarm_device_error": (
            "⚠️ Сирена будильника требует внимания. Проверьте Family Assistant в HA."
        ),
        "alarm_device_recovered": "✅ Сирена будильника снова отвечает.",
        "task_assigned": "📋 Новая задача: {id} · {title}",
        "task_review": "📸 Отчёт ждёт проверки: {id} · {title}",
        "task_reminder": "📋 Скоро срок задачи: {id} · {title} · {due_at}",
        "task_personal_due": "🔒 Личное напоминание: {id} · {title} · {due_at}",
        "task_overdue": "⚠️ {member}: просрочена задача {id} · {title}. Нужна проверка родителя.",
        "task_incident_closed": (
            "✅ Ситуация с просрочкой задачи {id} у {member} закрыта. "
            "Начисленные баллы проверяются отдельно."
        ),
        "shopping_approval": "🛒 Покупка ждёт одобрения: {id} · {title}",
        "price_watch_drop": (
            "📉 Цена снизилась: {name} — {old_price} → {new_price} {currency}. Проверьте ссылку."
        ),
        "price_watch_available": ("✅ Снова в наличии: {name} — {price_text}. Проверьте ссылку."),
        "pantry_expiry": (
            "📦 Напоминание о запасах: для «{name}» записан срок годности: {expires_on}. "
            "Проверьте вручную. Это не оценка безопасности продукта; остаток не изменён."
        ),
        "school_preparation_reminder": (
            "🎒 Подготовка к школе для {member} на {date} · {timetable}. "
            "Закреплённая рутина: {routine}. Что взять: {materials}. "
            "Проверьте всё и запустите рутину сами; автоматически ничего не запускалось."
        ),
        "court_appeal": "⚖️ Апелляция ждёт решения родителя: {id}",
        "court_appeal_resolved": "⚖️ Апелляция {id}: {decision}. Причина — в карточке суда.",
        "court_weekly": "{weekly_proclamation}",
    },
    "uk": {
        "routine_step": "🪜 {title} · Крок {step_number}: {step_title}",
        "routine_overdue": (
            "🪜 {member} · {title}: ще чекаємо крок «{step_title}». Автоматичного штрафу немає."
        ),
        "routine_closed": "✅ {member} · {title}: {step_title} — {outcome}.",
        "routine_completed": "✅ Рутину завершено: {title}",
        "calendar_reminder": "📅 {title} · {start}\n{location}\n{preparation}",
        "reward_requested": (
            "🎁 {member}: заявка {id} · {title}. Резерв: {cost} балів. Потрібна перевірка батьків."
        ),
        "reward_changed": "🎁 {id} · {title}: {status}. Причина: {reason}",
        "reward_expired": "🎁 {id} · {title}: термін заявки минув, її резерв балів звільнено.",
        "network_plan_finished": (
            "🌐 План мережі {id}: {status}. "
            "Подробиці й результат перевірки — у картці домашньої мережі."
        ),
        "network_watch_cleared": (
            "✅ Усі раніше невідомі пристрої перевірено. "
            "Сповіщення про нові пристрої в мережі закрито. Відкрийте картку домашньої мережі."
        ),
        "alarm_challenge": "⏰ Перевірка підйому: {question} = ?\nВиберіть відповідь кнопкою.",
        "alarm_missed": "⏰ {member}: підйом не підтверджено за 30 хвилин.",
        "alarm_closed": "✅ {member}: перевірку підйому закрито ({stage}).",
        "alarm_device_error": (
            "⚠️ Сирена будильника потребує уваги. Перевірте Family Assistant у HA."
        ),
        "alarm_device_recovered": "✅ Сирена будильника знову відповідає.",
        "task_assigned": "📋 Нове завдання: {id} · {title}",
        "task_review": "📸 Звіт чекає перевірки: {id} · {title}",
        "task_reminder": "📋 Скоро термін завдання: {id} · {title} · {due_at}",
        "task_personal_due": "🔒 Особисте нагадування: {id} · {title} · {due_at}",
        "task_overdue": (
            "⚠️ {member}: прострочено завдання {id} · {title}. Потрібна перевірка батьків."
        ),
        "task_incident_closed": (
            "✅ Ситуацію з простроченням завдання {id} у {member} закрито. "
            "Нараховані бали перевіряються окремо."
        ),
        "shopping_approval": "🛒 Покупка чекає схвалення: {id} · {title}",
        "price_watch_drop": (
            "📉 Ціна знизилась: {name} — {old_price} → {new_price} {currency}. Перевірте посилання."
        ),
        "price_watch_available": (
            "✅ Знову в наявності: {name} — {price_text}. Перевірте посилання."
        ),
        "pantry_expiry": (
            "📦 Нагадування про запаси: для «{name}» записано термін придатності: {expires_on}. "
            "Перевірте вручну. Це не оцінка безпечності продукту; залишок не змінено."
        ),
        "school_preparation_reminder": (
            "🎒 Підготовка до школи для {member} на {date} · {timetable}. "
            "Закріплена рутина: {routine}. Що взяти: {materials}. "
            "Перевірте все й запустіть рутину самі; автоматично нічого не запускалося."
        ),
        "court_appeal": "⚖️ Апеляція чекає рішення батьків: {id}",
        "court_appeal_resolved": "⚖️ Апеляція {id}: {decision}. Причина — у картці суду.",
        "court_weekly": "{weekly_proclamation}",
    },
}


def _school_reminder_source_current(event, state):
    """Recheck current sources when no dispatch-time clock is available here.

    The durable worker checks the real current time both before claim and before
    transport.  Target resolution and rendering use ``created_at`` only to
    validate the same source-bound event without pretending it is the current
    delivery time.
    """
    from ..domain.school_reminders import delivery_allowed

    try:
        created_at = timestamp(event.get("created_at"), "created_at")
        return delivery_allowed(state, event, created_at)
    except (DomainError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return False


def _school_reminder_content(event, target, state, language):
    from ..domain import recurrence, school

    if not _school_reminder_source_current(event, state):
        raise DeliveryError("delivery_revoked")
    data = event["data"]
    member = state.get("members", {}).get(data["member"])
    timetable = state.get("school", {}).get("timetables", {}).get(data["timetable_id"])
    routine = state.get("routines", {}).get(data["routine_id"])
    if not all(isinstance(item, dict) for item in (member, timetable, routine)):
        raise DeliveryError("notification_template_invalid")
    recipient = state.get("members", {}).get(event["recipient"], {})
    if not isinstance(recipient, dict) or target.get("id") != recipient.get("telegram_id"):
        raise DeliveryError("delivery_revoked")
    labels = {
        "en": ("none recorded", "more"),
        "ru": ("не указано", "ещё"),
        "uk": ("не вказано", "ще"),
    }.get(language, ("none recorded", "more"))
    values = {
        "member": (member.get("name"), 80),
        "timetable": (timetable.get("title"), 120),
        "routine": (routine.get("title"), 255),
    }
    if any(
        not isinstance(value, str) or not value.strip() or len(value) > maximum
        for value, maximum in values.values()
    ):
        raise DeliveryError("notification_template_invalid")
    day = recurrence.local_date(data["date"])
    rows = [
        row
        for row in school._occurrences(state, [timetable], day)
        if row.get("timetable_id") == data["timetable_id"] and row.get("date") == data["date"]
    ]
    materials = []
    seen = set()
    for row in rows:
        if not isinstance(row.get("materials"), list):
            raise DeliveryError("notification_template_invalid")
        for material in row["materials"]:
            if not isinstance(material, str) or not material.strip() or len(material) > 120:
                raise DeliveryError("notification_template_invalid")
            normalized = material.strip()
            identity = normalized.casefold()
            if identity not in seen:
                seen.add(identity)
                materials.append(normalized)
    visible = materials[:MAX_SCHOOL_MATERIALS]
    materials_text = ", ".join(visible) if visible else labels[0]
    if len(materials) > len(visible):
        materials_text += f" … (+{len(materials) - len(visible)} {labels[1]})"
    return {
        **{key: value.strip() for key, (value, _maximum) in values.items()},
        "date": data["date"],
        "materials": materials_text,
    }


def targets(event, state):
    from ..domain.task_delivery import TASK_EVENTS, current_task_event

    recipient, key = event["recipient"], event["key"]
    if key == "network_unreviewed_devices":
        from .watch_messages import targets as watch_targets

        return watch_targets(state, event)
    if key == "family_digest":
        from ..domain.digests import target as digest_target

        selected = digest_target(state, event, event.get("created_at"))
        return [selected] if selected is not None else []
    if key in TASK_EVENTS and not current_task_event(state, event):
        return []
    language = state["settings"]["language"]
    group = state["telegram"].get("group_id")
    if key == "telegram_poll_reply":
        from .poll_delivery import current

        if not current(event, state, event.get("created_at")):
            return []
        actor = state["members"][event["data"]["actor"]]
        return [
            {"channel": "telegram", "id": event["data"]["chat_id"], "language": actor["language"]}
        ]
    if key == "telegram_reply":
        from .reply_delivery import current

        if not current(event, state, event.get("created_at")):
            return []
        actor = state["members"].get(event["data"]["actor"], {})
        chat = event["data"]["chat_id"]
        if (
            actor.get("active")
            and actor.get("telegram_id")
            and chat in {actor["telegram_id"], group}
        ):
            return [{"channel": "telegram", "id": chat, "language": actor["language"]}]
        return []
    if key == "pantry_expiry":
        from ..domain.pantry_expiry import current_event

        if recipient != "parents" or not current_event(state, event):
            return []
        people = [
            member
            for member in state["members"].values()
            if member.get("active")
            and member.get("telegram_id")
            and member.get("role") in {"parent", "owner"}
        ]
        return [
            {
                "channel": "telegram",
                "id": member["telegram_id"],
                "language": member["language"],
            }
            for member in people
        ]
    if key == "school_preparation_reminder":
        if not _school_reminder_source_current(event, state):
            return []
        member = state.get("members", {}).get(recipient, {})
        if not member.get("telegram_id"):
            return []
        return [
            {
                "channel": "telegram",
                "id": member["telegram_id"],
                "language": member.get("language", language),
            }
        ]
    if recipient == "family":
        return [{"channel": "telegram", "id": group, "language": language}] if group else []
    people = [
        m
        for m in state["members"].values()
        if m["active"]
        and m.get("telegram_id")
        and ((recipient == "parents" and m["role"] in {"parent", "owner"}) or m["id"] == recipient)
    ]
    return [
        {"channel": "telegram", "id": m["telegram_id"], "language": m["language"]} for m in people
    ]


def render(event, target, state, *, now=None):
    if event.get("key") == "network_unreviewed_devices":
        from datetime import UTC, datetime

        from .watch_messages import render as render_watch

        return render_watch(state, event, target, now if now is not None else datetime.now(UTC))
    from ..domain.task_access import personal_task
    from ..domain.task_delivery import TASK_EVENTS

    task = state.get("tasks", {}).get(event.get("data", {}).get("id"))
    if personal_task(task) or event["key"] == "task_personal_due":
        if event["key"] not in TASK_EVENTS or target not in targets(event, state):
            raise DeliveryError("delivery_revoked")
    if event["key"] == "family_digest":
        from datetime import UTC, datetime

        from .digest_messages import render as render_digest

        return render_digest(event, target, state, now if now is not None else datetime.now(UTC))
    language = target.get("language", "en")
    t = MESSAGES.get(language, MESSAGES["en"])
    data = dict(event["data"])
    if event["key"] == "telegram_poll_reply":
        from datetime import UTC, datetime

        from .poll_delivery import current
        from .polls import render_reply

        now = now if now is not None else datetime.now(UTC)
        if not current(event, state, now) or target.get("id") != data["chat_id"]:
            raise DeliveryError("delivery_revoked")
        result = {
            **render_reply(state, data["actor"], data["descriptor"], now, language),
            "chat_id": target["id"],
        }
        if data.get("reply_to"):
            result["reply_parameters"] = {
                "message_id": data["reply_to"],
                "allow_sending_without_reply": True,
            }
    elif event["key"] == "telegram_reply":
        from datetime import UTC, datetime

        from .reply_delivery import current

        if not current(event, state, now if now is not None else datetime.now(UTC)) or (
            "actor_revision" in data and target.get("id") != data["chat_id"]
        ):
            raise DeliveryError("delivery_revoked")
        result = {"chat_id": target["id"], "text": data["text"][:4000]}
        if data.get("reply_to"):
            result["reply_parameters"] = {
                "message_id": data["reply_to"],
                "allow_sending_without_reply": True,
            }
    elif event["key"] == "school_preparation_reminder":
        template = t.get(event["key"])
        if template is None:
            raise DeliveryError("notification_template_missing")
        data.update(_school_reminder_content(event, target, state, language))
        result = {"chat_id": target["id"], "text": template.format(**data)[:4000]}
    else:
        template = t.get(event["key"])
        if template is None:
            raise DeliveryError("notification_template_missing")
        record_id = data.get("id", "")
        record = next(
            (
                state[bucket][record_id]
                for bucket in ("tasks", "shopping", "court", "reward_requests")
                if record_id in state.get(bucket, {})
            ),
            {},
        )
        data["title"] = record.get("title", record.get("name", data.get("title", "")))
        data["member"] = state["members"].get(data.get("member"), {}).get("name", "")
        if event["key"].startswith("routine_"):
            from .routines import COPY as ROUTINE_COPY

            data["step_number"] = data.get("step", 0) + 1
            if "outcome" in data:
                data["outcome"] = ROUTINE_COPY.get(language, ROUTINE_COPY["en"])[data["outcome"]]
        if event["key"] == "calendar_reminder":
            from datetime import datetime
            from zoneinfo import ZoneInfo

            if not data["all_day"]:
                data["start"] = (
                    datetime.fromisoformat(data["start"])
                    .astimezone(ZoneInfo(data["timezone"]))
                    .strftime("%Y-%m-%d %H:%M")
                    + " · "
                    + data["timezone"]
                )
            data["preparation"] = "\n".join("☐ " + item for item in data["preparation"])
        if event["key"] == "reward_changed":
            labels = {
                "en": {
                    "approved": "approved by a parent",
                    "rejected": "declined",
                    "cancelled": "cancelled",
                    "fulfilled": "marked provided by a parent",
                    "refunded": "points refunded",
                },
                "ru": {
                    "approved": "одобрено родителем",
                    "rejected": "отклонено",
                    "cancelled": "отменено",
                    "fulfilled": "родитель отметил предоставление",
                    "refunded": "баллы возвращены",
                },
                "uk": {
                    "approved": "схвалено батьками",
                    "rejected": "відхилено",
                    "cancelled": "скасовано",
                    "fulfilled": "батьки відзначили надання",
                    "refunded": "бали повернено",
                },
            }
            data["status"] = labels.get(language, labels["en"])[data["status"]]
        if event["key"] == "court_appeal_resolved":
            labels = {
                "en": {"uphold": "original points upheld", "reverse": "original points reversed"},
                "ru": {"uphold": "исходные баллы оставлены", "reverse": "исходные баллы отменены"},
                "uk": {"uphold": "початкові бали залишено", "reverse": "початкові бали скасовано"},
            }
            data["decision"] = labels.get(language, labels["en"])[data["decision"]]
        if event["key"] == "court_weekly":
            from datetime import datetime
            from zoneinfo import ZoneInfo

            report = state.get("court_reports", {}).get(data["report_id"])
            if not report:
                raise DeliveryError("notification_template_invalid")
            zone = ZoneInfo(report["timezone"])
            data["period"] = (
                " → ".join(
                    datetime.fromisoformat(report[key]).astimezone(zone).strftime("%Y-%m-%d %H:%M")
                    for key in ("start", "end")
                )
                + " · "
                + report["timezone"]
            )
            rows = []
            for row in report["rows"]:
                name = state["members"].get(row["member"], {}).get("name", "—")
                rows.append(
                    f"{name}: +{row['active_positives']} / {row['active_negatives']} "
                    f"= {row['total']:+d}"
                )
            data["summary"] = "\n".join(rows) or {
                "en": "No score events in this period.",
                "ru": "За этот период начислений нет.",
                "uk": "За цей період нарахувань немає.",
            }.get(language, "No score events in this period.")
            from .presentation import threshold_lines

            thresholds = threshold_lines(report, state["members"].values(), language)
            if thresholds:
                data["summary"] += "\n\n" + "\n".join(thresholds)
            if language in {"ru", "uk"}:
                template = (
                    (
                        "⚖️ Недельные итоги: {period}\n{summary}\n\nБаллы не обнулены. "
                        "Итог зафиксирован на момент публикации; "
                        "последующие исправления остаются в журнале."
                    )
                    if language == "ru"
                    else (
                        "⚖️ Тижневі підсумки: {period}\n{summary}\n\nБали не обнулено. "
                        "Підсумок зафіксовано на час публікації; "
                        "подальші виправлення залишаються в журналі."
                    )
                )
        if event["key"] == "network_plan_finished":
            labels = {
                "en": {
                    "applied": "applied and verified",
                    "rolled_back": "compensated; check DHCP recovery",
                    "review_required": "needs your review",
                    "failed": "not applied",
                    "expired": "temporary exception ended; previous mode verified",
                },
                "ru": {
                    "applied": "применён и проверен",
                    "rolled_back": "выполнен откат; проверьте восстановление DHCP",
                    "review_required": "нужна ваша проверка",
                    "failed": "не применён",
                    "expired": "временное исключение завершено; прежний режим проверен",
                },
                "uk": {
                    "applied": "застосовано й перевірено",
                    "rolled_back": "виконано відкат; перевірте відновлення DHCP",
                    "review_required": "потрібна ваша перевірка",
                    "failed": "не застосовано",
                    "expired": "тимчасовий виняток завершено; попередній режим перевірено",
                },
            }
            data["status"] = labels.get(language, labels["en"]).get(data["status"], data["status"])
            if record_id.startswith("K") and event["data"]["status"] == "rolled_back":
                data["status"] = {
                    "en": "previous profile restored",
                    "ru": "прежний профиль восстановлен",
                    "uk": "попередній профіль відновлено",
                }[language]
        result = {"chat_id": target["id"], "text": template.format(**data)[:4000]}
    result["link_preview_options"] = {"is_disabled": True}
    if event["key"] == "telegram_reply" and data.get("network_plan_id"):
        plan = state["network"].get("kid_plans", {}).get(data["network_plan_id"], {})
        if plan.get("status") == "preview" and plan.get("actor") == data["actor"]:
            labels = {
                "en": ("Confirm", "Cancel"),
                "ru": ("Подтвердить", "Отменить"),
                "uk": ("Підтвердити", "Скасувати"),
            }[language]
            result["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": label, "callback_data": f"fn:{action}:{plan['id']}"}
                        for label, action in zip(labels, ("confirm", "cancel"), strict=True)
                    ]
                ]
            }
    if event["key"] == "alarm_challenge":
        # Callback carries only the run, nonce and choice. Actor identity comes from Telegram.
        buttons = [
            {"text": str(answer), "callback_data": f"fa:{data['run_id']}:{data['nonce']}:{answer}"}
            for answer in data["choices"]
        ]
        if any(len(button["callback_data"].encode()) > 64 for button in buttons):
            raise DeliveryError("notification_template_invalid")
        result["reply_markup"] = {"inline_keyboard": [buttons]}
    if event["key"] == "routine_step" and data.get("nonce"):
        from .routines import COPY as ROUTINE_COPY

        callback_data = f"fr:{data['run_id']}:{data['step']}:{data['revision']}:{data['nonce']}"
        if len(callback_data.encode()) > 64:
            raise DeliveryError("notification_template_invalid")
        result["reply_markup"] = {
            "inline_keyboard": [
                [
                    {
                        "text": ROUTINE_COPY.get(language, ROUTINE_COPY["en"])["confirm"],
                        "callback_data": callback_data,
                    }
                ]
            ]
        }
    if event["key"] == "telegram_reply" and data.get("proposal_id"):
        proposal = state.get("proposals", {}).get(data["proposal_id"], {})
        if proposal.get("status") == "pending" and proposal.get("actor") == data["actor"]:
            labels = {
                "en": ("Confirm", "Cancel"),
                "ru": ("Подтвердить", "Отменить"),
                "uk": ("Підтвердити", "Скасувати"),
            }[language]
            result["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": label, "callback_data": f"fp:{action}:{proposal['id']}"}
                        for label, action in zip(labels, ("confirm", "cancel"), strict=True)
                    ]
                ]
            }
    return result
