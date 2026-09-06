"""Kid Control text commands expose schedules, not the private router inventory."""

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from ..domain.validation import DomainError, timestamp
from ..network.kids import DAYS, minute
from .intents import find_member

COPY = {
    "en": {
        "preview": "Review only — nothing changed",
        "queued": "Queued — awaiting router read-back",
        "applied": "Configuration applied and verified",
        "cancelled": "Plan cancelled",
        "profile": "Internet profile",
        "stale": "No verified current profile",
        "pause": "Paused",
        "resume": "Normal schedule",
        "grant": "Temporary access",
        "timed_pause": "Temporary pause",
        "schedule": "Schedule",
        "rate": "Rate limit",
        "until": "Until",
        "check": (
            "This verifies router configuration, not end-to-end connectivity. "
            "IPv6/FastTrack and downstream NAT need separate verification."
        ),
        "confirm": "Review and confirm: /netconfirm {id}\nCancel: /netcancel {id}",
        "devices": "Devices",
        "disabled": "Restrictions disabled",
        "empty": "No adopted profiles.",
        "time": "Last observation",
        "timer": (
            "Temporary access requires verified expiry and restart guards on the "
            "router. A router restart ends this exception early."
        ),
        "status_unknown": "Status unknown: refresh router data",
        "status_allowed": "Configured access: Allowed",
        "status_blocked": "Configured access: Blocked",
        "next_allowed": "Next allowed",
        "next_blocked": "Next blocked",
        "remaining": "Remaining",
        "temporary_expiry": "Temporary access until",
        "temporary_pause_expiry": "Temporary pause until",
        "min_unit": "min",
        "weekly_schedule": "Weekly schedule",
    },
    "ru": {
        "preview": "Только проверка плана — ничего не изменено",
        "queued": "В очереди — ждём повторной проверки роутера",
        "applied": "Настройки применены и проверены",
        "cancelled": "План отменён",
        "profile": "Профиль интернета",
        "stale": "Нет проверенного текущего профиля",
        "pause": "Пауза",
        "resume": "Обычное расписание",
        "grant": "Временный доступ",
        "timed_pause": "Временная пауза",
        "schedule": "Расписание",
        "rate": "Лимит скорости",
        "until": "До",
        "check": (
            "Это проверка настроек роутера, а не сквозного доступа. IPv6/FastTrack "
            "и устройства за другим NAT проверяются отдельно."
        ),
        "confirm": "Проверьте и подтвердите: /netconfirm {id}\nОтмена: /netcancel {id}",
        "devices": "Устройства",
        "disabled": "Ограничения выключены",
        "empty": "Нет переданных под управление профилей.",
        "time": "Последнее наблюдение",
        "timer": (
            "Временное исключение требует проверенных таймеров окончания и запуска "
            "на роутере. Перезагрузка роутера завершит исключение досрочно."
        ),
        "status_unknown": "Статус неизвестен: обновите данные роутера",
        "status_allowed": "По настройкам: доступ разрешён",
        "status_blocked": "По настройкам: доступ заблокирован",
        "next_allowed": "Следующее включение",
        "next_blocked": "Следующая блокировка",
        "remaining": "Осталось",
        "temporary_expiry": "Временный доступ до",
        "temporary_pause_expiry": "Временная пауза до",
        "min_unit": "мин",
        "weekly_schedule": "Еженедельное расписание",
    },
    "uk": {
        "preview": "Лише перевірка плану — нічого не змінено",
        "queued": "У черзі — чекаємо повторної перевірки роутера",
        "applied": "Налаштування застосовано й перевірено",
        "cancelled": "План скасовано",
        "profile": "Профіль інтернету",
        "stale": "Немає перевіреного поточного профілю",
        "pause": "Пауза",
        "resume": "Звичайний розклад",
        "grant": "Тимчасовий доступ",
        "timed_pause": "Тимчасова пауза",
        "schedule": "Розклад",
        "rate": "Ліміт швидкості",
        "until": "До",
        "check": (
            "Це перевірка налаштувань роутера, а не наскрізного доступу. "
            "IPv6/FastTrack і пристрої за іншим NAT перевіряються окремо."
        ),
        "confirm": "Перевірте й підтвердьте: /netconfirm {id}\nСкасувати: /netcancel {id}",
        "devices": "Пристрої",
        "disabled": "Обмеження вимкнено",
        "empty": "Немає переданих під керування профілів.",
        "time": "Останнє спостереження",
        "timer": (
            "Тимчасовий виняток потребує перевірених таймерів завершення та "
            "запуску на роутері. Перезавантаження роутера завершить виняток "
            "достроково."
        ),
        "status_unknown": "Статус невідомий: оновіть дані роутера",
        "status_allowed": "За налаштуваннями: доступ дозволено",
        "status_blocked": "За налаштуваннями: доступ заблоковано",
        "next_allowed": "Наступне увімкнення",
        "next_blocked": "Наступне блокування",
        "remaining": "Залишилося",
        "temporary_expiry": "Тимчасовий доступ до",
        "temporary_pause_expiry": "Тимчасова пауза до",
        "min_unit": "хв",
        "weekly_schedule": "Щотижневий розклад",
    },
}

FIELDS = {
    "en": {
        "disabled": "Restrictions",
        "paused": "Forced pause",
        "rate-limit": "Rate limit",
        "enabled": "Enabled",
        "off": "Disabled",
        "yes": "Yes",
        "no": "No",
        "empty": "None",
        "unlimited": "Unlimited rate",
        "days": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    },
    "ru": {
        "disabled": "Ограничения",
        "paused": "Принудительная пауза",
        "rate-limit": "Лимит скорости",
        "enabled": "Включены",
        "off": "Выключены",
        "yes": "Да",
        "no": "Нет",
        "empty": "Нет",
        "unlimited": "Без лимита скорости",
        "days": ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"),
    },
    "uk": {
        "disabled": "Обмеження",
        "paused": "Примусова пауза",
        "rate-limit": "Ліміт швидкості",
        "enabled": "Увімкнено",
        "off": "Вимкнено",
        "yes": "Так",
        "no": "Ні",
        "empty": "Немає",
        "unlimited": "Без обмеження швидкості",
        "days": ("Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"),
    },
}


def diff_line(key, change, language):
    t = FIELDS.get(language, FIELDS["en"])
    day = key.removeprefix("tur-")
    label = t.get(key, key)
    if day in DAYS:
        label = t["days"][DAYS.index(day)]
        if key.startswith("tur-"):
            label += " · " + t["unlimited"]

    def value(v):
        if key == "disabled":
            return t["off"] if v == "true" else t["enabled"]
        if key == "paused":
            return t["yes"] if v == "true" else t["no"]
        return v or t["empty"]

    return f"{label}: {value(change['before'])} → {value(change['after'])}"


def parsed(state, content, now):
    command, _, tail = content.strip().partition(" ")
    command = command.casefold()
    aliases = {
        "/интернет": "/internet",
        "/інтернет": "/internet",
        "/нетпауза": "/netpause",
        "/нетпродовжити": "/netgrant",
        "/нетпродлить": "/netgrant",
    }
    command = aliases.get(command, command)
    parts = [p.strip() for p in tail.split("|")]
    if command in {"/netconfirm", "/netcancel"}:
        if len(parts) != 1 or not re.fullmatch(r"K\d{6}", parts[0]):
            raise DomainError("invalid_field", "id")
        return "mikrotik.kid_" + ("apply" if command == "/netconfirm" else "cancel"), {
            "id": parts[0],
            "confirmed": True,
        }
    if command == "/internet":
        return "read.network", {"member": find_member(state, tail)} if tail.strip() else {}
    if command in {
        "/netpause",
        "/netresume",
        "/netgrant",
        "/netblock",
        "/netuntil",
        "/netschedule",
        "/netlimit",
    }:
        expected = (
            1 if command in {"/netpause", "/netresume"} else (3 if command == "/netschedule" else 2)
        )
        if len(parts) != expected:
            raise DomainError("invalid_field", "command")
        payload = {"member": find_member(state, parts[0])}
        payload["mode"] = {
            "/netpause": "pause",
            "/netresume": "resume",
            "/netgrant": "grant",
            "/netblock": "timed_pause",
            "/netuntil": "grant",
            "/netschedule": "schedule",
            "/netlimit": "rate",
        }[command]
        if command in {"/netgrant", "/netblock"}:
            if not re.fullmatch(r"\d{1,4}", parts[1]):
                raise DomainError("invalid_field", "minutes")
            payload["minutes"] = int(parts[1])
        elif command == "/netuntil":
            minutes = minute(parts[1])
            local = now.astimezone(ZoneInfo(state["settings"]["timezone"]))
            end = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                minutes=minutes
            )
            if end <= local:
                end += timedelta(days=1)
            payload["until"] = end.isoformat()
        elif command == "/netschedule":
            groups = {
                "weekdays": DAYS[:5],
                "будни": DAYS[:5],
                "будні": DAYS[:5],
                "weekends": DAYS[5:],
                "выходные": DAYS[5:],
                "вихідні": DAYS[5:],
                "all": DAYS,
                "все": DAYS,
                "усі": DAYS,
            }
            days = groups.get(parts[1].casefold())
            if days is None:
                raise DomainError("invalid_field", "days")
            payload["schedule"] = dict.fromkeys(days, parts[2])
        elif command == "/netlimit":
            payload["rate_limit"] = parts[1]
        return "mikrotik.kid_plan", payload
    # Strict whole-message patterns; names/aliases must resolve exactly once.
    patterns = (
        (r"(?:выключи|отключи|вимкни)\s+интернет\s+(.+)", "/netpause"),
        (r"(?:выключи|отключи|вимкни)\s+інтернет\s+(.+)", "/netpause"),
        (r"(?:включи|увімкни)\s+(.+?)\s+(?:интернет|інтернет)", "/netresume"),
        (r"(?:включи|увімкни)\s+(?:интернет|інтернет)\s+(.+)", "/netresume"),
        (r"(?:что|що)\s+(?:с|з)\s+(?:интернетом|інтернетом)\s+[уy]\s+(.+?)\??", "/internet"),
        (
            r"(?:дай|дозволь)\s+(.+?)\s+(?:интернет|інтернет)\s+на\s+(\d{1,4})\s+(?:минут\w*|хвилин\w*)",
            "/netgrant",
        ),
        (r"(?:верни|поверни)\s+(.+?)\s+(?:обычное расписание|звичайний розклад)", "/netresume"),
        (r"pause internet for (.+)", "/netpause"),
        (r"resume internet for (.+)", "/netresume"),
        (r"give (.+?) internet for (\d{1,4}) minutes", "/netgrant"),
    )
    for pattern, equivalent in patterns:
        match = re.fullmatch(pattern, content.strip().rstrip(".!?"), re.I)
        if match:
            return parsed(state, equivalent + " " + " | ".join(match.groups()), now)
    return None


def render_plan(result, view, language):
    t = COPY[language]
    member = next((m["name"] for m in view["members"] if m["id"] == result["member"]), "")
    lines = [
        f"🌐 {result['id']} · {member}",
        t.get(result["mode"], result["mode"]),
        t.get(result["status"], result["status"]),
    ]
    for key, change in result.get("diff", {}).items():
        lines.append(diff_line(key, change, language))
    if result.get("until"):
        from ..domain.validation import timestamp

        local = timestamp(result["until"], "until").astimezone(
            ZoneInfo(view["settings"]["timezone"])
        )
        lines += [
            f"{t['until']}: {local:%Y-%m-%d %H:%M} ({view['settings']['timezone']})",
            t["timer"],
        ]
    lines.append(t["check"])
    if result["status"] == "preview":
        lines.append(t["confirm"].format(id=result["id"]))
    return "\n".join(lines)[:3800]


def status(view, member, language):
    t = COPY[language]
    data = view["kid_control"]
    profiles = [p for p in data["profiles"] if not member or p["member"] == member]
    if member and not profiles:
        raise DomainError("network_kid_unmanaged")
    tz_str = view.get("settings", {}).get("timezone", "UTC")
    tz = ZoneInfo(tz_str)
    lines = []
    mode_labels = {
        "schedule": t["resume"],
        "paused": t["pause"],
        "unrestricted": t["disabled"],
    }
    for p in profiles:
        who = next(m["name"] for m in view["members"] if m["id"] == p["member"])
        lines.append(f"🌐 {t['profile']}: {who}")

        st = p.get("status")
        is_dict = isinstance(st, dict)
        mode = st.get("mode") if is_dict else None
        allows = st.get("allows") if is_dict else None
        is_known = mode in {"schedule", "paused", "unrestricted"} and isinstance(allows, bool)

        if not is_known:
            lines.append(f"⚠️ {t['status_unknown']}")
        else:
            lines.append(mode_labels[mode])
            lines.append(t["status_allowed"] if allows else t["status_blocked"])
            if allows and st.get("remaining_minutes") is not None:
                lines.append(f"{t['remaining']}: {st['remaining_minutes']} {t['min_unit']}")
            if st.get("next_change_at"):
                local_next = timestamp(st["next_change_at"], "next_change_at").astimezone(tz)
                next_label = t["next_allowed"] if st.get("next_allows") else t["next_blocked"]
                lines.append(f"{next_label}: {local_next:%Y-%m-%d %H:%M} ({tz_str})")
            if st.get("temporary_until"):
                local_temp = timestamp(st["temporary_until"], "temporary_until").astimezone(tz)
                temp_label = (
                    t["temporary_pause_expiry"]
                    if st.get("temporary_mode") == "timed_pause"
                    else t["temporary_expiry"]
                )
                lines.append(f"{temp_label}: {local_temp:%Y-%m-%d %H:%M} ({tz_str})")

        current = p.get("observed")
        if current is None:
            lines.append(t["stale"])
            continue
        lines.append(f"📅 {t['weekly_schedule']}:")
        lines.extend(
            f"{FIELDS[language]['days'][i]}: {current[d] or '—'}" for i, d in enumerate(DAYS)
        )
        lines.append(t["devices"] + ": " + ", ".join(p["device_names"]))
    if lines:
        lines += [f"{t['time']}: {data['observed_at']}", t["check"]]
    return "\n".join(lines)[:3800] or t["empty"]
