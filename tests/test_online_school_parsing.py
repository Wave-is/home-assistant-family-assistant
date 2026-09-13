"""Fictional wire schemas, not copied school records. No network or credentials."""

import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from html import escape

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.online_school import parsing

BASE = "https://school.example.invalid"
NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def header(children=None):
    user = {
        "group": "parent",
        "children": children if children is not None else {"101": "Synthetic Learner"},
        "medical": "SYNTHETIC-NOT-FOR-EXPORT",
        "email": "private@example.invalid",
        "address": "SYNTHETIC-NOT-FOR-EXPORT",
        "canteen": {"balance": 900},
    }
    value = {"user": user, "current_child": {"id": 999}, "session": "SYNTHETIC-NOT-FOR-EXPORT"}
    return "<app-header :header_data='" + escape(json.dumps(value), quote=True) + "'></app-header>"


def lesson(lesson_id=501):
    return {
        "id": lesson_id,
        "date": "2026-09-13T21:00:00Z",
        "order_num_in_day": 1,
        "replacement": 0,
        "replacement_info": None,
        "canceled": 0,
        "lesson_num": 1,
        "start_time": "09:00",
        "end_time": "09:45",
        "subject_name": "Synthetic Science",
        "class_room_name": "Room A",
        "teacher_name": "Synthetic Teacher",
        "teacher_id": 808,
        "teacher_picture": "/private/avatar",
        "teacher_zoom_url": None,
        "topic": "Matter",
        "topic_html": "<p>Matter</p>",
        "homework": "Read chapter 2",
        "homework_html": "<p>Read chapter 2</p>",
        "description": "unused",
        "work_time": "20",
        "homework_files": [],
        "lesson_files": [],
        "grades": [],
    }


def diary(week=3, *, rows=True, student=101):
    start = date(2026, 9, 14) + timedelta(weeks=week - 3)
    days = [
        {
            "day_name": "Synthetic day",
            "date": (start + timedelta(days=i)).strftime("%d.%m.%Y"),
            "is_holiday": False,
            "carry_date": "",
            "lessons": [],
        }
        for i in range(7)
    ]
    if rows:
        days[0]["lessons"] = [lesson(500 + week)]
    return {
        "week_days": days,
        "student": {"user_id": student, "user_name": "Synthetic Learner"},
        "week_title": "Synthetic week",
        "week": week,
        "prev_week": {"num": week - 1, "url": "https://evil.example.invalid/other/student"},
        "next_week": {"num": week + 1, "url": "/daybook/other-child"},
    }


def journal(*, student=101):
    return {
        "next_month": {"num": 2, "url": "/untrusted"},
        "prev_month": {"num": 0, "url": ""},
        "month_num": "1",
        "month_abs_num": "09",
        "month_title": "Synthetic September",
        "grades": [],
        "absents": [],
        "dates": [f"{day:02}" for day in range(1, 31)],
        "subjects": {"201": {"id": 201, "name": "Synthetic Science", "private": "discard"}},
        "lessons": [],
        "student": {"user_id": student, "user_name": "Synthetic Learner"},
    }


def test_discovery_projects_only_reviewable_ids_names_not_current_child_or_sensitive_fields():
    assert parsing.students(
        header({"101": "Synthetic <b>Learner</b>", "202": "Second learner"})
    ) == [
        {"id": "101", "name": "Synthetic Learner"},
        {"id": "202", "name": "Second learner"},
    ]
    assert parsing.students(header({})) == []


@pytest.mark.parametrize(
    "value",
    [
        "",
        "<script>window.header_data={}</script>",
        header() + header(),
        "<app-header :header_data='not-json'></app-header>",
    ],
)
def test_header_without_exact_single_json_attribute_fails(value):
    with pytest.raises(DomainError):
        parsing.students(value)


def test_student_shape_is_an_explicit_allowlisted_ui_branch():
    value = {
        "user": {"group": "student", "id": 101, "name": "Synthetic Learner", "medical": "discard"}
    }
    html = "<app-header :header_data='" + escape(json.dumps(value), quote=True) + "'></app-header>"
    assert parsing.students(html) == [{"id": "101", "name": "Synthetic Learner"}]


def test_csrf_requires_one_token_in_same_origin_post_auth_form():
    html = (
        '<form method="POST" action="/auth"><input type="hidden" name="_token" '
        'value="synthetic-csrf"></form>'
    )
    assert parsing.csrf(html, BASE) == "synthetic-csrf"
    for invalid in (
        html + html,
        html.replace("/auth", "https://evil.example.invalid/auth"),
        html.replace("POST", "GET"),
        '<input name="_token" value="fake">',
    ):
        with pytest.raises(DomainError, match="online_school_auth_failed"):
            parsing.csrf(invalid, BASE)


def test_snapshot_uses_local_day_not_previous_utc_date_and_exact_allowlisted_fields():
    result = parsing.snapshot([diary()], journal(), "101", "Europe/Kyiv", NOW, BASE)
    assert set(result) == {
        "student_id",
        "student_name",
        "timezone",
        "source_url",
        "coverage_start",
        "coverage_end",
        "lessons",
        "grades",
        "absences",
    }
    item = result["lessons"][0]
    assert item["date"] == "2026-09-14" and item["start"] == "09:00"
    assert item["estimated_minutes"] == 20
    assert result["grades"] == result["absences"] == []
    assert set(item) == {
        "id",
        "date",
        "start",
        "end",
        "subject",
        "room",
        "teacher",
        "topic",
        "homework",
        "estimated_minutes",
        "cancelled",
        "replacement",
        "links",
        "attachments",
    }
    assert not any(
        key in json.dumps(result) for key in ("teacher_id", "picture", "private", "description")
    )


def test_verified_empty_days_are_valid_but_missing_arrays_or_blank_objects_fail():
    assert (
        parsing.snapshot([diary(rows=False)], journal(), "101", "UTC", NOW, BASE)["lessons"] == []
    )
    for bad in ({}, {**diary(), "week_days": []}, {**diary(), "week_days": None}):
        with pytest.raises(DomainError, match="online_school_invalid_response"):
            parsing.snapshot([bad], journal(), "101", "UTC", NOW, BASE)


def test_text_html_links_and_metadata_are_sanitized_without_fetching():
    data = diary()
    row = data["week_days"][0]["lessons"][0]
    row.update(
        homework="",
        homework_html=(
            "<p>Read <b>chapter</b></p><script>private()</script>"
            '<a href="https://resource.example.invalid/chapter">resource</a>'
            '<img src="https://evil.example.invalid/tracker">'
            '<a href="javascript:alert(1)">bad</a>'
            '<a href="https://user:pass@example.invalid/x">bad2</a>'
        ),
        teacher_zoom_url="https://meeting.example.invalid/lesson",
        canceled=1,
        replacement=1,
    )
    row["homework_files"] = [
        {
            "id": 991,
            "original_name": "<b>Worksheet</b>.pdf",
            "ext": "pdf",
            "size": 1024,
            "download_url": "https://evil.example.invalid/download",
            "uploader": "discard",
        }
    ]
    result = parsing.snapshot([data], journal(), "101", "UTC", NOW, BASE)["lessons"][0]
    assert result["homework"] == "Read chapter\nresourcebadbad2"
    assert result["links"] == [
        "https://resource.example.invalid/chapter",
        "https://meeting.example.invalid/lesson",
    ]
    assert result["attachments"] == [
        {"id": "991", "name": "Worksheet.pdf", "ext": "pdf", "size": 1024}
    ]
    assert result["cancelled"] is True and result["replacement"] is True


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,secret",
        "http://example.invalid/",
        "https://127.0.0.1/a",
        "https://localhost./a",
        "https://host.local/a",
        "https://example.invalid/x?token=secret",
        "https://user:pass@example.invalid/a",
        "https://example.invalid\\@evil.example.invalid/",
    ],
)
def test_unsafe_presentation_links_are_discarded(url):
    assert parsing.https_url(url, base_url=BASE) is None


def test_nonempty_shipped_ui_grades_preserve_special_marks_absence_and_stable_correction_id():
    value = journal()
    value["grades"] = {
        "14": {
            "201": [
                {"grade_value": "Н/А", "comment": "Not assessed", "name": "Practice"},
                {"grade_value": 0, "comment": "Actual explicit zero", "name": "Quiz"},
            ]
        },
        "Semester": {"201": [{"grade_value": "pass", "name": "Term", "comment": ""}]},
    }
    value["absents"] = {"15": {"201": {"comment": "Excused"}}}
    result = parsing.journal(value, "101", "Europe/Kyiv", NOW)
    assert [row["value"] for row in result["grades"]] == ["Н/А", "0", "pass"]
    assert result["grades"][0]["date"] == "2026-09-14"
    assert result["grades"][-1]["date"] is None
    assert result["grades"][-1]["period"] == "Semester"
    assert "value" not in result["absences"][0]
    value["grades"]["14"]["201"][0].update(grade_value="8", comment="Corrected")
    assert (
        parsing.journal(value, "101", "Europe/Kyiv", NOW)["grades"][0]["id"]
        == result["grades"][0]["id"]
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"month_num": "9"},
        {"grades": [1]},
        {"absents": None},
        {"grades": {"31": {"201": [{"grade_value": 8}]}}},
        {"grades": {"01": {"999": [{"grade_value": 8}]}}},
        {"grades": {"01": {"201": [{"grade_value": float("nan")}]}}},
    ],
)
def test_malformed_journal_is_not_a_fake_empty_result(patch):
    with pytest.raises(DomainError, match="online_school_invalid_response"):
        parsing.journal({**journal(), **patch}, "101", "UTC", NOW)


def test_calendar_month_is_separate_from_academic_month_and_year_is_not_guessed():
    value = journal()
    value.update(month_num="5", month_abs_num="01", grades={"02": {"201": [{"grade_value": 9}]}})
    assert (
        parsing.journal(value, "101", "UTC", datetime(2027, 1, 4, tzinfo=UTC))["grades"][0]["date"]
        == "2027-01-02"
    )
    with pytest.raises(DomainError, match="online_school_invalid_response"):
        parsing.journal(value, "101", "UTC", NOW)


def test_same_day_subject_index_in_another_calendar_month_is_a_different_grade():
    september = journal()
    september["grades"] = {"14": {"201": [{"grade_value": 8}]}}
    october = {**deepcopy(september), "month_num": "2", "month_abs_num": "10"}
    first = parsing.journal(september, "101", "UTC", NOW)["grades"][0]
    second = parsing.journal(october, "101", "UTC", datetime(2026, 10, 14, tzinfo=UTC))["grades"][0]
    assert first["id"] != second["id"]


@pytest.mark.parametrize(
    "kind",
    [
        "identity",
        "duplicate_day",
        "reversed_time",
        "bad_flag",
        "huge_text",
        "many_files",
        "changed_duplicate",
    ],
)
def test_malformed_diary_is_rejected(kind):
    data = diary()
    row = data["week_days"][0]["lessons"][0]
    if kind == "identity":
        data["student"]["user_id"] = 202
    elif kind == "duplicate_day":
        data["week_days"][1]["date"] = data["week_days"][0]["date"]
    elif kind == "reversed_time":
        row["end_time"] = "08:00"
    elif kind == "bad_flag":
        row["canceled"] = "yes"
    elif kind == "huge_text":
        row["homework"] = "x" * 4001
    elif kind == "many_files":
        row["homework_files"] = [{}] * 21
    else:
        data["week_days"][1]["lessons"] = [deepcopy(row)]
    with pytest.raises(DomainError):
        parsing.snapshot([data], journal(), "101", "UTC", NOW, BASE)


def test_adjacent_numbers_never_use_server_student_or_url():
    assert parsing.adjacent(diary()) == [2, 4]
    value = diary(1)
    value["prev_week"] = {"num": 0, "url": ""}
    assert parsing.adjacent(value) == [2]
    assert parsing.adjacent({**value, "next_week": {"num": 1, "url": "/anything"}}) == []


def test_nullable_file_lists_mean_no_files_but_other_nonlists_remain_invalid():
    data = diary()
    row = data["week_days"][0]["lessons"][0]
    row.update(homework_files=None, lesson_files=None)
    assert parsing.diary(data, "101", BASE)["lessons"][0]["attachments"] == []
    for invalid in ({}, "", 0, False):
        row["homework_files"] = invalid
        with pytest.raises(DomainError, match="online_school_invalid_response"):
            parsing.diary(data, "101", BASE)


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', '{"grade":NaN}', "[" * 26 + "0" + "]" * 26])
def test_json_duplicate_nonfinite_and_depth_are_rejected(value):
    with pytest.raises(DomainError, match="online_school_invalid_response"):
        parsing.load_json(value)


def test_snapshot_passes_actual_domain_normalizer_not_a_provider_only_mock():
    from custom_components.family_assistant.domain.online_school import normalize_snapshot

    parsed = parsing.snapshot(
        [diary(2), diary(), diary(4)], journal(), "101", "Europe/Kyiv", NOW, BASE
    )
    normalized = normalize_snapshot(parsed)
    assert normalized["student_id"] == parsed["student_id"]
    assert normalized["lessons"] == parsed["lessons"]
    assert normalized["coverage_start"] == "2026-09-07"


def test_huge_numbers_return_stable_errors_instead_of_python_conversion_exceptions():
    with pytest.raises(DomainError, match="online_school_invalid_response"):
        parsing.period("9" * 5000)
    value = journal()
    value["grades"] = {"14": {"201": [{"grade_value": 10**400}]}}
    with pytest.raises(DomainError, match="online_school_invalid_response"):
        parsing.journal(value, "101", "UTC", NOW)
