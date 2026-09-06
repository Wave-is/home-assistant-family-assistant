"""Localized notification envelopes; no parse_mode for user-supplied text."""

from ..notifications import DeliveryError

MESSAGES = {
    "en": {
        "network_plan_finished": (
            "🌐 Network plan {id}: {status}. Details and read-back are on the Home network card."
        ),
        "alarm_challenge": "⏰ Wake-up check: {question} = ?\nChoose the answer below.",
        "alarm_missed": "⏰ {member}: wake-up was not confirmed within 30 minutes.",
        "alarm_closed": "✅ {member}: the wake-up incident is closed ({stage}).",
        "alarm_device_error": "⚠️ The wake-up siren needs attention. Check Family Assistant in HA.",
        "alarm_device_recovered": "✅ The wake-up siren is responding again.",
        "task_assigned": "📋 New task: {id} · {title}",
        "task_review": "📸 Review requested: {id} · {title}",
        "task_reminder": "📋 Task due soon: {id} · {title} · {due_at}",
        "task_overdue": "⚠️ {member}: task overdue: {id} · {title}. Parent review is needed.",
        "task_incident_closed": (
            "✅ The overdue incident for {member}'s task {id} is closed. "
            "Any recorded points remain separately reviewable."
        ),
        "shopping_approval": "🛒 Purchase approval requested: {id} · {title}",
        "court_appeal": "⚖️ An appeal needs a parent's review: {id}",
        "court_appeal_resolved": "⚖️ Appeal {id}: {decision}. The reason is in the court card.",
        "court_weekly": (
            "⚖️ Weekly results: {period}\n{summary}\n\nBalances were not reset. "
            "This report records the result at publication; later corrections remain in the ledger."
        ),
    },
    "ru": {
        "network_plan_finished": (
            "🌐 План сети {id}: {status}. "
            "Подробности и результат проверки — в карточке домашней сети."
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
        "task_overdue": "⚠️ {member}: просрочена задача {id} · {title}. Нужна проверка родителя.",
        "task_incident_closed": (
            "✅ Ситуация с просрочкой задачи {id} у {member} закрыта. "
            "Начисленные баллы проверяются отдельно."
        ),
        "shopping_approval": "🛒 Покупка ждёт одобрения: {id} · {title}",
        "court_appeal": "⚖️ Апелляция ждёт решения родителя: {id}",
        "court_appeal_resolved": "⚖️ Апелляция {id}: {decision}. Причина — в карточке суда.",
        "court_weekly": (
            "⚖️ Недельные итоги: {period}\n{summary}\n\nБаллы не обнулены. "
            "Итог зафиксирован на момент публикации; последующие исправления остаются в журнале."
        ),
    },
    "uk": {
        "network_plan_finished": (
            "🌐 План мережі {id}: {status}. "
            "Подробиці й результат перевірки — у картці домашньої мережі."
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
        "task_overdue": (
            "⚠️ {member}: прострочено завдання {id} · {title}. Потрібна перевірка батьків."
        ),
        "task_incident_closed": (
            "✅ Ситуацію з простроченням завдання {id} у {member} закрито. "
            "Нараховані бали перевіряються окремо."
        ),
        "shopping_approval": "🛒 Покупка чекає схвалення: {id} · {title}",
        "court_appeal": "⚖️ Апеляція чекає рішення батьків: {id}",
        "court_appeal_resolved": "⚖️ Апеляція {id}: {decision}. Причина — у картці суду.",
        "court_weekly": (
            "⚖️ Тижневі підсумки: {period}\n{summary}\n\nБали не обнулено. "
            "Підсумок зафіксовано на час публікації; подальші виправлення залишаються в журналі."
        ),
    },
}


def targets(event, state):
    recipient, key = event["recipient"], event["key"]
    language = state["settings"]["language"]
    group = state["telegram"].get("group_id")
    if key == "telegram_reply":
        actor = state["members"].get(event["data"]["actor"], {})
        chat = event["data"]["chat_id"]
        if (
            actor.get("active")
            and actor.get("telegram_id")
            and chat in {actor["telegram_id"], group}
        ):
            return [{"channel": "telegram", "id": chat, "language": actor["language"]}]
        return []
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


def render(event, target, state):
    language = target.get("language", "en")
    t = MESSAGES.get(language, MESSAGES["en"])
    data = dict(event["data"])
    if event["key"] == "telegram_reply":
        result = {"chat_id": target["id"], "text": data["text"][:4000]}
        if data.get("reply_to"):
            result["reply_parameters"] = {
                "message_id": data["reply_to"],
                "allow_sending_without_reply": True,
            }
    else:
        template = t.get(event["key"])
        if template is None:
            raise DeliveryError("notification_template_missing")
        record_id = data.get("id", "")
        record = next(
            (
                state[bucket][record_id]
                for bucket in ("tasks", "shopping", "court")
                if record_id in state[bucket]
            ),
            {},
        )
        data["title"] = record.get("title", record.get("name", ""))
        data["member"] = state["members"].get(data.get("member"), {}).get("name", "")
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
