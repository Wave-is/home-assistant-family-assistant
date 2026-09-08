"""Exact spoken review phrases resolve only a frozen proposal reference."""

import re

from ..domain.validation import DomainError

PHRASES = {
    "confirm the proposal": "confirm",
    "cancel the proposal": "reject",
    "подтверждаю предложение": "confirm",
    "отмени предложение": "reject",
    "підтверджую пропозицію": "confirm",
    "скасуй пропозицію": "reject",
}

VOICE_PREVIEW = {
    "en": (
        "Please check the proposal. Nothing has changed yet: {preview}. "
        "In this conversation, say confirm the proposal or cancel the proposal. "
        "It expires in five minutes."
    ),
    "ru": (
        "Проверьте предложение. Пока ничего не изменено: {preview}. "
        "В этой беседе скажите: подтверждаю предложение или отмени предложение. "
        "Оно действует пять минут."
    ),
    "uk": (
        "Перевірте пропозицію. Поки нічого не змінено: {preview}. "
        "У цій розмові скажіть: підтверджую пропозицію або скасуй пропозицію. "
        "Вона діє п'ять хвилин."
    ),
}


def parse_reply(content, refs):
    """No guessing a recent/global proposal, generic yes, or model fallback."""
    phrase = " ".join(content.casefold().split()).strip(" .?!")
    action = PHRASES.get(phrase)
    if action is None:
        return None
    if (
        not isinstance(refs, (list, tuple))
        or len(refs) != 1
        or not isinstance(refs[0], str)
        or re.fullmatch(r"P[0-9a-f]{20}", refs[0]) is None
    ):
        raise DomainError("context_required")
    return "conversation." + action, {"id": refs[0]}
