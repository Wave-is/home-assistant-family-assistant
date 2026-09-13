"""Explicit private Telegram drawing requests, separate from model dialogue."""

import asyncio
import re

from ..assistant.image_jobs import project
from ..domain.validation import DomainError

COPY = {
    "en": {
        "private": "Send /draw in your private chat with the bot. Images and history stay private.",
        "usage": "Use /draw followed by an image description. /images shows your latest requests.",
        "disabled": (
            "Image generation is not configured or is disabled. "
            "Ask the household owner to enable an image provider in Options."
        ),
        "queued": (
            "🎨 Request {id}: {status}. /images shows progress. Generation and Telegram "
            "delivery can remain uncertain; this request is never blindly repeated."
        ),
        "empty": "No image requests.",
        "result": "🎨 Generated image · {id}",
        "busy": "The private image queue or retained-image limit is full. Try later.",
        "queued_state": "queued",
        "submitting": "submitting",
        "polling": "generating",
        "ready": "ready",
        "delivering": "sending",
        "complete": "sent",
        "failed": "failed",
        "cancelled": "cancelled",
        "uncertain": "uncertain — not automatically repeated",
    },
    "ru": {
        "private": "Отправьте /draw в личный чат боту. Изображения и история остаются личными.",
        "usage": "Напишите /draw и описание изображения. /images покажет последние запросы.",
        "disabled": (
            "Генерация изображений не настроена или выключена. "
            "Владелец семьи может включить провайдера в настройках интеграции."
        ),
        "queued": (
            "🎨 Запрос {id}: {status}. Ход работы — /images. "
            "Результат генерации или отправки может остаться неопределённым; "
            "такой запрос не повторяется вслепую."
        ),
        "empty": "Запросов изображений пока нет.",
        "result": "🎨 Созданное изображение · {id}",
        "busy": "Очередь или лимит сохранённых личных изображений заполнены. Попробуйте позже.",
        "queued_state": "в очереди",
        "submitting": "отправляется",
        "polling": "создаётся",
        "ready": "готово",
        "delivering": "отправка изображения",
        "complete": "отправлено",
        "failed": "ошибка",
        "cancelled": "отменён",
        "uncertain": "результат неизвестен — без автоматического повтора",
    },
    "uk": {
        "private": (
            "Надішліть /draw в особистий чат боту. Зображення та історія залишаються особистими."
        ),
        "usage": "Напишіть /draw та опис зображення. /images покаже останні запити.",
        "disabled": (
            "Генерацію зображень не налаштовано або вимкнено. "
            "Власник сім’ї може ввімкнути провайдера в налаштуваннях інтеграції."
        ),
        "queued": (
            "🎨 Запит {id}: {status}. Перебіг роботи — /images. "
            "Результат генерації чи надсилання може залишитися невідомим; "
            "такий запит не повторюється наосліп."
        ),
        "empty": "Запитів зображень ще немає.",
        "result": "🎨 Створене зображення · {id}",
        "busy": "Черга або ліміт збережених особистих зображень заповнені. Спробуйте пізніше.",
        "queued_state": "у черзі",
        "submitting": "надсилається",
        "polling": "створюється",
        "ready": "готово",
        "delivering": "надсилання зображення",
        "complete": "надіслано",
        "failed": "помилка",
        "cancelled": "скасовано",
        "uncertain": "результат невідомий — без автоматичного повтору",
    },
}


def prompt(content):
    value = content.strip()
    if value.casefold() == "/draw":
        return ""
    match = re.fullmatch(
        r"(?:/draw|draw|нарисуй|намалюй|(?:generate|create)\s+(?:an?\s+)?image(?:\s+of)?|(?:сгенерируй|создай)\s+(?:изображение|картинку)|(?:згенеруй|створи)\s+(?:зображення|картинку))\s+(.+)",
        value,
        re.I,
    )
    return match[1].strip() if match else None


def status(row, words):
    return words.get(
        "queued_state" if row["status"] == "queued" else row["status"], words["failed"]
    )


def current_result(state, data):
    row = state.get("image_jobs", {}).get(data.get("image_job_id"), {})
    return bool(
        "conversation" in state["settings"]["modules"]
        and row.get("status") in {"failed", "uncertain"}
        and row.get("actor") == data.get("actor")
        and row.get("actor_revision") == data.get("actor_revision")
        and row.get("provider_scope") == data.get("image_provider_scope")
        and row.get("chat_id") == data.get("chat_id")
        and row.get("bot_id") == data.get("bot_id")
    )


async def enqueue(manager, actor, message, content, operation_id, command_guard):
    requested = prompt(content)
    history = content.strip().casefold() == "/images"
    if requested is None and not history:
        return None
    state = manager.runtime.engine.snapshot()
    command_guard(state)
    words = COPY[state["members"][actor]["language"]]
    if message["chat"].get("type") != "private":
        return words["private"]
    if history:
        return (
            "\n".join(row["id"] + " · " + status(row, words) for row in project(state, actor))
            or words["empty"]
        )
    if not requested:
        return words["usage"]
    service = getattr(manager.runtime, "image_generation", None)
    if service is None or not service.config["enabled"]:
        return words["disabled"]
    try:
        row = await service.enqueue(
            actor,
            requested,
            operation_id,
            bot_id=manager.bot["id"],
            chat_id=message["chat"]["id"],
            reply_to=message.get("message_id"),
            command_guard=command_guard,
        )
    except DomainError as error:
        if error.code in {"provider_not_configured", "module_disabled"}:
            return words["disabled"]
        if error.code == "image_busy":
            return words["busy"]
        raise
    command_guard(manager.runtime.engine.snapshot())
    return words["queued"].format(id=row["id"], status=status(row, words))


async def run(manager):
    while not manager._stopped:
        try:
            await manager.runtime.engine.async_wait_writable()
            manager._manager_guard()
            service = getattr(manager.runtime, "image_generation", None)
            if service is not None:

                async def deliver(job, data, mime, guard, selected=service):
                    manager._manager_guard()
                    if selected is not manager.runtime.image_generation:
                        raise DomainError("forbidden")
                    guard()
                    receipt = await manager.client.send_photo(
                        job["chat_id"],
                        data,
                        mime,
                        COPY[job["language"]]["result"].format(id=job["id"]),
                    )
                    manager._manager_guard()
                    guard()
                    return receipt

                await service.step(manager.bot["id"], deliver)
                manager.runtime.health.pop("images", None)
        except DomainError as error:
            if error.code not in {"forbidden", "module_disabled", "backup_in_progress", "conflict"}:
                manager.runtime.health["images"] = "image_unavailable"
        except OSError:
            manager.runtime.health["images"] = "storage_error"
        await asyncio.sleep(5)
