"""Starter routine templates catalog."""

from __future__ import annotations

import copy
from typing import Any

from .validation import DomainError

SUPPORTED_LANGUAGES = frozenset({"en", "ru", "uk"})

_HOLIDAY_SKIP_CONDITION: dict[str, Any] = {
    "kind": "any",
    "conditions": [
        {"kind": "mode", "mode": "holidays"},
        {"kind": "mode", "mode": "vacation"},
    ],
}

_CATALOG: dict[str, dict[str, Any]] = {
    "en": {
        "morning": {
            "title": "Morning Routine",
            "description": "Gentle morning checklist to wake up and start the day smoothly.",
            "skip_when": _HOLIDAY_SKIP_CONDITION,
            "steps": [
                "Wake up and stretch",
                "Check that you are ready and out of bed",
                "Wash face and brush teeth",
                "Have a healthy breakfast",
                "Check and grab your bag",
            ],
        },
        "evening": {
            "title": "Evening Wind-Down",
            "description": "Quiet evening steps to wrap up the day and prepare for rest.",
            "skip_when": None,
            "steps": [
                "Tidy up room and workspace",
                "Pick and prepare tomorrow's clothes",
                "Pack and check your bag for tomorrow",
                "Get ready for bed and sleep",
            ],
        },
        "school_bag": {
            "title": "School Bag Packing",
            "description": "Quick check to ensure everything needed for school is packed.",
            "skip_when": _HOLIDAY_SKIP_CONDITION,
            "steps": [
                "Check tomorrow's timetable",
                "Pack required textbooks",
                "Pack workbooks and notebooks",
                "Take a water bottle",
            ],
        },
    },
    "ru": {
        "morning": {
            "title": "Утренний распорядок",
            "description": "Мягкий чеклист, чтобы спокойно проснуться и начать новый день.",
            "skip_when": _HOLIDAY_SKIP_CONDITION,
            "steps": [
                "Проснуться и потянуться",
                "Проверить готовность подняться с кровати",
                "Умыться и почистить зубы",
                "Позавтракать",
                "Проверить и взять рюкзак",
            ],
        },
        "evening": {
            "title": "Вечерний распорядок",
            "description": "Спокойные шаги, чтобы завершить дела и подготовиться ко сну.",
            "skip_when": None,
            "steps": [
                "Навести порядок в комнате и на столе",
                "Приготовить одежду на завтра",
                "Собрать и проверить рюкзак на завтра",
                "Подготовиться ко сну",
            ],
        },
        "school_bag": {
            "title": "Сбор рюкзака в школу",
            "description": "Быстрый чеклист, чтобы ничего не забыть к урокам.",
            "skip_when": _HOLIDAY_SKIP_CONDITION,
            "steps": [
                "Проверить расписание уроков на завтра",
                "Сложить нужные учебники",
                "Сложить тетради и пенал",
                "Взять бутылку с водой",
            ],
        },
    },
    "uk": {
        "morning": {
            "title": "Ранковий розпорядок",
            "description": "Лагідний чекліст, щоб спокійно прокинутися і почати новий день.",
            "skip_when": _HOLIDAY_SKIP_CONDITION,
            "steps": [
                "Прокинутися та потягнутися",
                "Перевірити готовність піднятися з ліжка",
                "Вмитися та почистити зуби",
                "Поснідати",
                "Перевірити та взяти наплічник",
            ],
        },
        "evening": {
            "title": "Вечірній розпорядок",
            "description": "Спокійні кроки, щоб завершити справи та підготуватися до сну.",
            "skip_when": None,
            "steps": [
                "Навести лад у кімнаті та на робочому місці",
                "Підготувати одяг на завтра",
                "Зібрати та перевірити наплічник на завтра",
                "Підготуватися до сну",
            ],
        },
        "school_bag": {
            "title": "Збирання наплічника до школи",
            "description": "Швидкий чекліст, щоб нічого не забути до уроків.",
            "skip_when": _HOLIDAY_SKIP_CONDITION,
            "steps": [
                "Перевірити розклад уроків на завтра",
                "Покласти потрібні підручники",
                "Покласти зошити та пенал",
                "Узяти пляшку з водою",
            ],
        },
    },
}

_PRESET_ORDER: tuple[str, ...] = ("morning", "evening", "school_bag")


def templates(language: str) -> list[dict[str, Any]]:
    """Return localized preset routine templates.

    Raises DomainError('invalid_field', 'language') if language is unsupported.
    Returns deep copies on every call so definitions are never mutated globally.
    """
    if not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
        raise DomainError("invalid_field", "language")

    catalog_for_lang = _CATALOG[language]
    result: list[dict[str, Any]] = []

    for preset_id in _PRESET_ORDER:
        raw = catalog_for_lang[preset_id]
        steps: list[dict[str, Any]] = [
            {
                "title": step_title,
                "offset_minutes": 0,
                "confirmation": "manual",
                "completion_condition": None,
                "skip_when": None,
                "escalate_minutes": 15,
            }
            for step_title in raw["steps"]
        ]
        template = {
            "id": preset_id,
            "title": raw["title"],
            "description": raw["description"],
            "steps": steps,
            "skip_when": copy.deepcopy(raw["skip_when"]),
        }
        result.append(template)

    return result
