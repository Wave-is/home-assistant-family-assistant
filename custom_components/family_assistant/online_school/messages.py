"""Deterministic RU/UK/EN school answers; imported text never becomes an LLM prompt."""

import re
from copy import deepcopy
from datetime import timedelta
from zoneinfo import ZoneInfo

from ..domain.online_school import current_source
from ..telegram.context import PersonalReply

COPY = {
    "en": {
        "private": "School information is private. Ask me in our private chat.",
        "choose": "Choose a child: /school <name>, /homework <name>, /grades <name>.",
        "missing": (
            "No connected school data for this child yet. The owner can connect an account "
            "in Family Assistant settings → Services → Online school."
        ),
        "stale": "⚠️ Saved data; the school has not been checked recently.",
        "updated": "Last successful check",
        "schedule": "📚 Lessons",
        "homework": "🎒 Preparation for lessons",
        "grades": "📊 School marks",
        "empty": (
            "No entries published in the fetched period. "
            "This does not prove there is no homework or absence."
        ),
        "changes": "🔔 School update",
        "cancelled": "Cancelled",
        "minutes": "min",
        "more": "More details in the School dashboard.",
        "files": "Attachments in the school portal",
        "no_work": "Homework not published",
        "coverage": "Fetched period",
    },
    "ru": {
        "private": "Школьные данные — личные. Напиши мне в личный чат.",
        "choose": "Укажи ребёнка: /school <имя>, /homework <имя>, /grades <имя>.",
        "missing": (
            "Данных подключённой школы пока нет. Владелец может подключить кабинет: "
            "настройки Family Assistant → Сервисы → Онлайн-школа."
        ),
        "stale": "⚠️ Сохранённые данные: школа давно не проверялась или недоступна.",
        "updated": "Последняя успешная проверка",
        "schedule": "📚 Уроки",
        "homework": "🎒 Подготовка к урокам",
        "grades": "📊 Школьные оценки",
        "empty": (
            "В загруженном периоде записей нет. Это не доказывает отсутствие ДЗ или пропусков."
        ),
        "changes": "🔔 Изменения в школе",
        "cancelled": "Отменён",
        "minutes": "мин",
        "more": "Подробнее — на дашборде «Школа».",
        "files": "Вложения в школьном кабинете",
        "no_work": "ДЗ не опубликовано",
        "coverage": "Загруженный период",
    },
    "uk": {
        "private": "Шкільні дані — особисті. Напиши мені в приватний чат.",
        "choose": "Укажи дитину: /school <ім’я>, /homework <ім’я>, /grades <ім’я>.",
        "missing": (
            "Даних підключеної школи ще немає. Власник може підключити кабінет: "
            "налаштування Family Assistant → Сервіси → Онлайн-школа."
        ),
        "stale": "⚠️ Збережені дані: школу давно не перевіряли або вона недоступна.",
        "updated": "Остання успішна перевірка",
        "schedule": "📚 Уроки",
        "homework": "🎒 Підготовка до уроків",
        "grades": "📊 Шкільні оцінки",
        "empty": (
            "У завантаженому періоді записів немає. Це не доводить відсутність ДЗ або пропусків."
        ),
        "changes": "🔔 Зміни у школі",
        "cancelled": "Скасовано",
        "minutes": "хв",
        "more": "Докладніше — на дашборді «Школа».",
        "files": "Вкладення у шкільному кабінеті",
        "no_work": "ДЗ не опубліковане",
        "coverage": "Завантажений період",
    },
}


class SchoolReply(PersonalReply):
    def __new__(cls, text, scope=None):
        result = super().__new__(cls, text)
        result.school_scope = deepcopy(scope)
        return result


def reply_current(state, data):
    scope = data.get("school_context")
    if not isinstance(scope, list) or not scope or len(scope) > 8:
        return False
    actor = state.get("members", {}).get(data.get("actor"), {})
    for pin in scope:
        source = current_source(
            state, pin.get("id"), pin.get("generation"), pin.get("member_revision")
        )
        if source is None or source.get("snapshot_hash") != pin.get("snapshot_hash"):
            return False
        if actor.get("role") not in {"owner", "parent"} and (
            actor.get("role") != "child" or source["member"] != actor.get("id")
        ):
            return False
    return True


def describe(source, member_name, topic, day, language):
    t = COPY.get(language, COPY["en"])
    snapshot = source.get("snapshot") or {}
    lines = [f"{t[topic]} · {member_name} · {source['label']}"]
    if source.get("stale"):
        lines.append(t["stale"])
    if source.get("last_success"):
        lines.append(f"{t['updated']}: {source['last_success']}")
    if snapshot:
        lines.append(f"{t['coverage']}: {snapshot['coverage_start']} – {snapshot['coverage_end']}")
    if topic == "grades":
        rows = snapshot.get("grades", [])[-20:]
        for row in rows:
            lines.append(
                f"{row.get('date') or row['period']} · {row['subject']}: {row['value']}"
                + (f" — {row['comment']}" if row["comment"] else "")
            )
    else:
        lines.append(day)
        rows = [row for row in snapshot.get("lessons", []) if row["date"] == day]
        rows.sort(key=lambda row: (row["start"], row["id"]))
        for row in rows:
            line = f"{row['start']} · {row['subject']}"
            if row["cancelled"]:
                lines.append(line + " — " + t["cancelled"])
                continue
            if topic == "homework":
                line += "\n" + (row["homework"] or t["no_work"])
                if row["topic"]:
                    line += "\n" + row["topic"]
                if row["estimated_minutes"] is not None:
                    line += f"\n≈ {row['estimated_minutes']} {t['minutes']}"
                if row["attachments"]:
                    line += f"\n{t['files']}: " + ", ".join(
                        item["name"] for item in row["attachments"]
                    )
                if row["links"]:
                    line += "\n" + "\n".join(row["links"][:3])
            else:
                line += f" – {row['end']} · {row['room']}"
            lines.append(line)
    if not rows:
        lines.append(t["empty"])
    text = "\n".join(lines)
    return text if len(text) < 3800 else text[:3700] + "\n… " + t["more"]


def query(engine, actor, content, now, *, private, language):
    """Recognize school reads before general intent/model inference."""
    from ..domain.validation import DomainError
    from ..telegram.intents import find_member, normalize

    value = normalize(content)
    head, _, tail = content.strip().partition(" ")
    command = head.casefold()
    topic = {"/school": "schedule", "/homework": "homework", "/grades": "grades"}.get(command)
    if topic is None:
        if command.startswith("/") or not re.match(
            r"^(?:како\w*|что|когда|покажи|расписан\w*|дз\b|домашн\w*|урок\w*|оцен\w*|"
            r"що|коли|які?\w*|розклад\w*|оцін\w*|show\b|what\b|when\b|homework\b|school\b)",
            value,
        ):
            return None
        if re.search(r"\b(?:дз|д/з|homework|домашн\w*\s+(?:задан\w*|завдан\w*))\b", value):
            topic = "homework"
        elif re.search(r"\b(?:оцен\w*|оцін\w*|grades|marks)\b", value):
            topic = "grades"
        elif re.search(r"\b(?:школ\w*|урок\w*|school|lessons)\b", value):
            topic = "grades" if re.search(r"оцен\w*|оцін\w*|grades|marks", value) else "schedule"
        else:
            return None
    t = COPY.get(language, COPY["en"])
    if not private:
        return t["private"]
    state = engine.snapshot()
    if "school" not in state["settings"]["modules"]:
        return t["missing"]
    sources = engine.view(actor, now=now).get("school", {}).get("online", {}).get("sources", [])
    sources = [row for row in sources if row["enabled"]]
    target = None
    tokens = value.split()
    if command in {"/school", "/homework", "/grades"} and tail.strip():
        name = re.sub(
            r"\b(?:today|tomorrow|сегодня|завтра|сьогодні|\d{4}-\d{2}-\d{2})\b", "", tail
        ).strip()
        if name:
            try:
                target = find_member(state, name)
            except DomainError:
                return t["choose"]
    else:
        matches = set()
        for token in tokens:
            try:
                matches.add(find_member(state, token))
            except DomainError:
                pass
        if len(matches) > 1:
            return t["choose"]
        target = next(iter(matches), None)
    if target is None:
        ids = {row["member"] for row in sources}
        if len(ids) > 1:
            return t["choose"]
        target = next(iter(ids), None)
    selected = [row for row in sources if row["member"] == target]
    if not selected:
        return t["missing"]
    replies, pins = [], []
    for source in selected:
        local = now.astimezone(ZoneInfo(source["timezone"]))
        offset = 1 if topic == "homework" or re.search(r"\b(?:tomorrow|завтра)\b", value) else 0
        if re.search(r"\b(?:today|сегодня|сьогодні)\b", value):
            offset = 0
        day = (local.date() + timedelta(days=offset)).isoformat()
        explicit = re.search(r"\b\d{4}-\d{2}-\d{2}\b", value)
        if explicit:
            day = explicit.group()
        replies.append(describe(source, state["members"][target]["name"], topic, day, language))
        stored = state["school"]["online"]["sources"][source["id"]]
        pins.append(
            {key: stored[key] for key in ("id", "generation", "member_revision", "snapshot_hash")}
        )
    return SchoolReply("\n\n".join(replies)[:3900], pins)


def render(event, target, state, now):
    from ..notifications import DeliveryError
    from .delivery import current, targets

    if not current(state, event, now) or not any(
        all(target.get(key) == value for key, value in candidate.items())
        for candidate in targets(state, event, now)
    ):
        raise DeliveryError("delivery_revoked")
    data = event["data"]
    source = state["school"]["online"]["sources"][data["source"]]
    language = target["language"]
    t = COPY.get(language, COPY["en"])
    if data["kind"] == "prepare":
        text = describe(
            source, state["members"][source["member"]]["name"], "homework", data["date"], language
        )
    else:
        rows = [row for row in source["changes"] if row["id"] in data["changes"]]
        lines = [
            f"{t['changes']} · {state['members'][source['member']]['name']} · {source['label']}"
        ]
        for row in rows:
            facts = row.get("after") or row.get("before") or {}
            label = {"lesson": t["schedule"], "homework": t["homework"], "grade": t["grades"]}.get(
                row["kind"], t["changes"]
            )
            lines.append(
                f"{label} · {facts.get('date') or facts.get('period', '')} · "
                f"{facts.get('subject', '')}" + (f": {facts['value']}" if "value" in facts else "")
            )
        text = "\n".join(lines)[:3700] + "\n" + t["more"]
    return {"chat_id": target["id"], "text": text, "link_preview_options": {"is_disabled": True}}
