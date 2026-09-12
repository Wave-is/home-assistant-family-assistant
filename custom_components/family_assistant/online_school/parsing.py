"""Allowlisted portal parsing. Source HTML and private account fields never escape."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..domain.validation import DomainError

MAX_BODY = 2 * 1024 * 1024
_ID = re.compile(r"[1-9][0-9]{0,31}")
_DATE = re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}")
_TIME = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])(?::00)?")


def invalid():
    return DomainError("online_school_invalid_response")


def identifier(value):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise invalid()
    return value


def load_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise invalid()
            result[key] = item
        return result

    def constant(_value):
        raise invalid()

    try:
        result = json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise invalid() from None
    count = 0

    def inspect(item, depth=0):
        nonlocal count
        count += 1
        if depth > 24 or count > 60_000:
            raise invalid()
        if isinstance(item, dict):
            for child in item.values():
                inspect(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                inspect(child, depth + 1)

    inspect(result)
    return result


def https_url(value, *, base_url=None):
    """Public HTTPS presentation link, never a request/fetch instruction."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(ord(char) < 33 or char.isspace() for char in value) or "\\" in value:
        return None
    try:
        parts = urlsplit(urljoin(base_url, value) if base_url else value)
        host = parts.hostname
        if (
            parts.scheme != "https"
            or not host
            or parts.username
            or parts.password
            or parts.port not in {None, 443}
            or "%" in parts.netloc
            or "." not in host
            or host.rstrip(".").endswith((".local", ".localhost", ".internal"))
            or host.rstrip(".") == "localhost"
        ):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        secret_keys = {
            "_token",
            "token",
            "access_token",
            "session",
            "sessionid",
            "password",
            "email",
        }
        if any(key.casefold() in secret_keys for key, _ in parse_qsl(parts.query)):
            return None
        return urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return None


class _Text(HTMLParser):
    _HIDDEN = {"script", "style", "iframe", "object", "svg", "math", "template", "noscript"}
    _BREAK = {"p", "div", "br", "li", "tr", "section", "h1", "h2", "h3"}

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden = [], [], []
        self.base_url = base_url

    def handle_starttag(self, tag, attrs):
        if len(self.hidden) > 64:
            raise invalid()
        if tag in self._HIDDEN:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in self._BREAK:
            self.parts.append("\n")
        if tag == "a":
            url = https_url(dict(attrs).get("href"), base_url=self.base_url)
            if url and url not in self.links:
                self.links.append(url)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value, maximum, *, base_url=None):
    if value is None:
        return "", []
    if not isinstance(value, str) or len(value) > 32_000:
        raise invalid()
    parser = _Text(base_url)
    try:
        parser.feed(value)
        parser.close()
    except (ValueError, RecursionError):
        raise invalid() from None
    clean = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    clean = "".join(char for char in clean if char in "\n\t" or ord(char) >= 32)
    if len(clean) > maximum or len(parser.links) > 20:
        raise invalid()
    return clean, parser.links


def _text(value, maximum, *, required=False):
    clean, _ = plain(value, maximum)
    if required and not clean:
        raise invalid()
    return clean


class _Header(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag == "app-header":
            self.values.extend(value for name, value in attrs if name == ":header_data")


def students(html):
    parser = _Header()
    parser.feed(html)
    parser.close()
    if len(parser.values) != 1 or not isinstance(parser.values[0], str):
        raise DomainError("online_school_auth_failed")
    header = load_json(parser.values[0])
    user = header.get("user") if isinstance(header, dict) else None
    if not isinstance(user, dict):
        raise invalid()
    if user.get("group") == "parent":
        children = user.get("children")
        if not isinstance(children, dict) or len(children) > 20:
            raise invalid()
        return [
            {"id": identifier(key), "name": _text(name, 200, required=True)}
            for key, name in children.items()
        ]
    if user.get("group") == "student":
        # This branch follows the shipped UI; authenticated student acceptance
        # remains separate from the observed parent-account contract.
        return [
            {"id": identifier(user.get("id")), "name": _text(user.get("name"), 200, required=True)}
        ]
    raise DomainError("online_school_auth_failed")


class _CSRF(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url, self.forms, self.tokens = base_url, [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            action = urljoin(self.base_url + "/auth", attrs.get("action") or "/auth")
            self.forms.append(
                action == self.base_url + "/auth" and attrs.get("method", "get").lower() == "post"
            )
        elif tag == "input" and self.forms and self.forms[-1] and attrs.get("name") == "_token":
            self.tokens.append(attrs.get("value"))

    def handle_endtag(self, tag):
        if tag == "form" and self.forms:
            self.forms.pop()


def csrf(html, base_url):
    parser = _CSRF(base_url)
    parser.feed(html)
    parser.close()
    if len(parser.tokens) != 1:
        raise DomainError("online_school_auth_failed")
    value = parser.tokens[0]
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise DomainError("online_school_auth_failed")
    return value


def identity(data, student_id):
    if not isinstance(data, dict) or not isinstance(data.get("student"), dict):
        raise invalid()
    student = data["student"]
    if identifier(student.get("user_id")) != student_id:
        raise DomainError("online_school_student_mismatch")
    return _text(student.get("user_name"), 200, required=True)


def period(value):
    if isinstance(value, str) and value.isascii() and value.isdigit():
        if len(value) > 3:
            raise invalid()
        value = int(value)
    if type(value) is not int or not 1 <= value <= 60:
        raise invalid()
    return value


def adjacent(data):
    current = period(data.get("week"))
    result = []
    for key in ("prev_week", "next_week"):
        item = data.get(key)
        if item is None:
            continue
        if not isinstance(item, dict):
            raise invalid()
        number = item.get("num")
        if number in (None, 0, "0", "") and not item.get("url"):
            continue
        number = period(number)
        if number != current and number not in result:
            result.append(number)
    return result


def _day(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise invalid()
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        raise invalid() from None


def _time(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not (match := _TIME.fullmatch(value)):
        raise invalid()
    return match[1] + ":" + match[2]


def _flag(value):
    if value is None:
        return False
    if type(value) not in {int, bool} or value not in (0, 1):
        raise invalid()
    return bool(value)


def _estimate(value):
    if value is None or value == "":
        return None
    if type(value) is int:
        return value if 0 <= value <= 1440 else None
    if not isinstance(value, str) or len(value) > 100:
        raise invalid()
    match = re.fullmatch(
        r"\s*([0-9]{1,4})\s*(?:min|minutes?|хв|хвилин|мин|минут)?\.?\s*", value, re.IGNORECASE
    )
    return int(match[1]) if match and int(match[1]) <= 1440 else None


def _attachments(row):
    result = {}
    for field in ("homework_files", "lesson_files"):
        values = row.get(field, [])
        if values is None:
            values = []
        if not isinstance(values, list) or len(values) > 20:
            raise invalid()
        for value in values:
            if not isinstance(value, dict):
                raise invalid()
            key = identifier(value.get("id"))
            size = value.get("size")
            if isinstance(size, str) and size.isascii() and size.isdigit() and len(size) <= 16:
                size = int(size)
            ext = _text(value.get("ext"), 16).lstrip(".").lower()
            if (
                type(size) is not int
                or not 0 <= size <= 2**53 - 1
                or not re.fullmatch(r"[a-z0-9]{1,16}", ext)
            ):
                raise invalid()
            item = {
                "id": key,
                "name": _text(value.get("original_name"), 200, required=True),
                "ext": ext,
                "size": size,
            }
            if key in result and result[key] != item:
                raise invalid()
            result[key] = item
    if len(result) > 20:
        raise invalid()
    return list(result.values())


def diary(data, student_id, base_url, *, expected_week=None):
    name = identity(data, student_id)
    week = period(data.get("week"))
    if expected_week is not None and week != expected_week:
        raise invalid()
    days = data.get("week_days")
    if not isinstance(days, list) or len(days) != 7:
        raise invalid()
    dates, lessons = [], []
    for day in days:
        if not isinstance(day, dict):
            raise invalid()
        local_day = _day(day.get("date"))
        dates.append(local_day)
        rows = day.get("lessons")
        if isinstance(rows, dict):
            rows = list(rows.values())
        if not isinstance(rows, list) or len(rows) > 30:
            raise invalid()
        for row in rows:
            if not isinstance(row, dict):
                raise invalid()
            links, texts = [], {}
            for field, maximum in (("topic", 2000), ("homework", 4000)):
                html_text, html_links = plain(row.get(field + "_html"), maximum, base_url=base_url)
                raw_text, raw_links = plain(row.get(field), maximum, base_url=base_url)
                texts[field] = raw_text or html_text
                links.extend(raw_links + html_links)
            if zoom := https_url(row.get("teacher_zoom_url"), base_url=base_url):
                links.append(zoom)
            links = list(dict.fromkeys(links))
            if len(links) > 20:
                raise invalid()
            start, end = _time(row.get("start_time")), _time(row.get("end_time"))
            if start and end and end <= start:
                raise invalid()
            lessons.append(
                {
                    "id": "lesson:" + student_id + ":" + identifier(row.get("id")),
                    "date": local_day.isoformat(),
                    "start": start,
                    "end": end,
                    "subject": _text(row.get("subject_name"), 200, required=True),
                    "room": _text(row.get("class_room_name"), 200),
                    "teacher": _text(row.get("teacher_name"), 200),
                    **texts,
                    "estimated_minutes": _estimate(row.get("work_time")),
                    "cancelled": _flag(row.get("canceled")),
                    "replacement": _flag(row.get("replacement")),
                    "links": links,
                    "attachments": _attachments(row),
                }
            )
    if len(set(dates)) != 7 or any(
        day != dates[0] + timedelta(days=index) for index, day in enumerate(dates)
    ):
        raise invalid()
    return {"name": name, "dates": dates, "lessons": lessons}


def _mark_id(kind, student, period_label, subject, index):
    identity = json.dumps([student, period_label, subject, index], ensure_ascii=False).encode()
    return kind + ":" + hashlib.sha256(identity).hexdigest()[:32]


def journal(data, student_id, timezone, now):
    identity(data, student_id)
    try:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError
        local_now = now.astimezone(ZoneInfo(timezone))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise DomainError("online_school_invalid_config") from None
    month = period(data.get("month_abs_num"))
    academic = period(data.get("month_num"))
    if month > 12 or academic > 12 or month != ((academic + 7) % 12) + 1:
        raise invalid()
    year = local_now.year if month <= local_now.month else local_now.year - 1
    # The fetched endpoint is the current journal, not a guessed historical
    # school year. A future semester month cannot safely be inferred here.
    if month != local_now.month:
        year = None
    subjects = data.get("subjects")
    if not isinstance(subjects, dict) or len(subjects) > 100:
        raise invalid()
    names = {}
    for key, subject in subjects.items():
        if not isinstance(subject, dict) or identifier(subject.get("id")) != identifier(key):
            raise invalid()
        names[key] = _text(subject.get("name"), 200, required=True)
    dates = data.get("dates")
    if (
        not isinstance(dates, list)
        or len(dates) > 100
        or any(not isinstance(value, str) or len(value) > 200 for value in dates)
    ):
        raise invalid()

    def day(label):
        if re.fullmatch(r"[0-9]{1,2}", label):
            if year is None:
                raise invalid()
            try:
                return date(year, month, int(label)).isoformat()
            except ValueError:
                raise invalid() from None
        if _DATE.fullmatch(label):
            value = _day(label)
            if value.month != month:
                raise invalid()
            return value.isoformat()
        return None

    result = {"grades": [], "absences": []}
    for field, target, maximum in (("grades", "grades", 1000), ("absents", "absences", 500)):
        values = data.get(field)
        if values == []:
            values = {}
        if not isinstance(values, dict) or len(values) > 100:
            raise invalid()
        for label, by_subject in values.items():
            label = _text(label, 200, required=True)
            if not isinstance(by_subject, dict) or len(by_subject) > 100:
                raise invalid()
            for subject, items in by_subject.items():
                if subject not in names:
                    raise invalid()
                if field == "absents":
                    items = [items]
                if not isinstance(items, list) or len(items) > 100:
                    raise invalid()
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        raise invalid()
                    record = {
                        "id": _mark_id(
                            target,
                            student_id,
                            f"{year or local_now.year}:{month}:{label}",
                            subject,
                            index,
                        ),
                        "date": day(label),
                        "period": label,
                        "subject": names[subject],
                        "comment": _text(item.get("comment"), 1000),
                    }
                    if field == "grades":
                        value = item.get("grade_value")
                        if type(value) in {int, float}:
                            if type(value) is float and not math.isfinite(value):
                                raise invalid()
                            value = str(value)
                        record.update(
                            value=_text(value, 200, required=True),
                            kind=_text(item.get("name"), 200),
                        )
                    result[target].append(record)
                    if len(result[target]) > maximum:
                        raise invalid()
    return result


def snapshot(pages, marks, student_id, timezone, now, base_url):
    if not isinstance(pages, list) or not 1 <= len(pages) <= 3:
        raise invalid()
    parsed = [diary(page, student_id, base_url) for page in pages]
    dates = sorted({day for page in parsed for day in page["dates"]})
    if (dates[-1] - dates[0]).days > 34:
        raise invalid()
    lessons = {}
    for page in parsed:
        for row in page["lessons"]:
            if row["id"] in lessons and lessons[row["id"]] != row:
                raise invalid()
            lessons[row["id"]] = row
    if len(lessons) > 300:
        raise invalid()
    result = {
        "student_id": student_id,
        "student_name": parsed[0]["name"],
        "timezone": timezone,
        "source_url": base_url + "/daybook/" + student_id,
        "coverage_start": dates[0].isoformat(),
        "coverage_end": dates[-1].isoformat(),
        "lessons": sorted(lessons.values(), key=lambda row: (row["date"], row["start"], row["id"])),
        **journal(marks, student_id, timezone, now),
    }
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BODY:
        raise invalid()
    return result
