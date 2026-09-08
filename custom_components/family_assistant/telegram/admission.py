"""Private, source-bound inventory review replies. Never admission or router commands."""

from copy import deepcopy
from datetime import timedelta

from ..domain.validation import DomainError, fields, revision, timestamp
from ..network.admission_inventory import observation_token
from .context import PersonalReply

COPY = {
    "en": {
        "private": (
            "Network inventory is shown only in a parent's private chat. "
            "Send /unknown_devices here in private."
        ),
        "unavailable": (
            "Fresh complete router inventory is unavailable. Open Home network in HA "
            "and refresh it; no access rule was changed."
        ),
        "title": "Device inventory: {count} need owner review.",
        "unknown": "No reviewed name",
        "more": (
            "Showing {shown} of {count}. Full inventory and approvals are on the Home network card."
        ),
        "notice": (
            "This is inventory, not proof a device is online or malicious. "
            "HA matches are suggestions, not approval. "
            "No internet, DHCP or firewall settings were changed."
        ),
        "help": "\n/unknown_devices — private device inventory for parents",
    },
    "ru": {
        "private": (
            "Сетевой инвентарь доступен только в личном чате родителя. "
            "Отправьте боту /неизвестные в личку."
        ),
        "unavailable": (
            "Свежий полный инвентарь роутера недоступен. Откройте домашнюю сеть в HA "
            "и обновите данные; правила доступа не менялись."
        ),
        "title": "Инвентарь устройств: требуют проверки владельцем — {count}.",
        "unknown": "Название не подтверждено",
        "more": (
            "Показано {shown} из {count}. Полный список и подтверждения — в карточке домашней сети."
        ),
        "notice": (
            "Это инвентарь, а не доказательство, что устройство онлайн или опасно. "
            "Совпадение с HA — подсказка, не допуск. Интернет, DHCP и firewall не менялись."
        ),
        "help": "\n/неизвестные — инвентарь устройств в личном чате родителя",
    },
    "uk": {
        "private": (
            "Мережевий інвентар доступний лише в особистому чаті батьків. "
            "Надішліть боту /невідомі приватно."
        ),
        "unavailable": (
            "Свіжий повний інвентар роутера недоступний. Відкрийте домашню мережу в HA "
            "й оновіть дані; правила доступу не змінювались."
        ),
        "title": "Інвентар пристроїв: потребують перевірки власником — {count}.",
        "unknown": "Назву не підтверджено",
        "more": (
            "Показано {shown} з {count}. Повний список і підтвердження — у картці домашньої мережі."
        ),
        "notice": (
            "Це інвентар, а не доказ, що пристрій онлайн або небезпечний. "
            "Збіг із HA — підказка, не допуск. Інтернет, DHCP і firewall не змінювались."
        ),
        "help": "\n/невідомі — інвентар пристроїв в особистому чаті батьків",
    },
}


class AdmissionReply(PersonalReply):
    def __new__(cls, value, scope=None):
        result = super().__new__(cls, value)
        result.scope = deepcopy(scope)
        return result


def read(view, now, *, private):
    if view.get("role") not in {"owner", "parent"}:
        raise DomainError("forbidden")
    actor = next(member for member in view["members"] if member["id"] == view["actor"])
    copy = COPY.get(actor.get("language"), COPY["en"])
    if not private:
        return copy["private"]
    projection = view.get("network", {}).get("admission")
    if not projection or projection.get("status") != "fresh":
        return copy["unavailable"]
    devices = [item for item in projection["devices"] if item["status"] == "unreviewed"]
    lines = [copy["title"].format(count=len(devices)), projection["observed_at"]]
    for item in devices[:10]:
        # All strings were bounded/projected by admission_inventory; use plain
        # text only, no Telegram parse mode or untrusted links/remote commands.
        name = item["candidate_name"] or copy["unknown"]
        lines.append(f"• {name[:60]} · {item['mac']} · {', '.join(item['addresses'][:2])}")
    lines.extend(
        [copy["more"].format(shown=min(10, len(devices)), count=len(devices)), copy["notice"]]
    )
    return AdmissionReply(
        "\n".join(lines),
        {
            "backend": projection["backend"],
            "token": projection["token"],
            "policy_revision": projection["policy_revision"],
            "actor_revision": actor["revision"],
            "expires_at": (now + timedelta(minutes=2)).isoformat(),
        },
    )


def current(state, data, now):
    """Revoke queued private details after source, policy, role or module changes."""
    try:
        scope = data.get("admission_context")
        if not isinstance(scope, dict) or data.get("private_context") is not True:
            return False
        fields(
            scope,
            {"backend", "token", "policy_revision", "actor_revision", "expires_at"},
            {"backend", "token", "policy_revision", "actor_revision", "expires_at"},
        )
        actor = state["members"][data["actor"]]
        if scope["policy_revision"] is not None:
            revision(scope["policy_revision"])
        return (
            "mikrotik" in state["settings"]["modules"]
            and actor.get("active") is True
            and actor.get("role") in {"owner", "parent"}
            and revision(scope["actor_revision"]) == revision(actor["revision"])
            and data.get("chat_id") == actor.get("telegram_id")
            and scope["backend"] == state["network"].get("backend")
            and scope["policy_revision"] == state["network"].get("admission", {}).get("revision")
            and timestamp(now, "now") < timestamp(scope["expires_at"], "expires_at")
            and scope["token"] == observation_token(state["network"], now)
        )
    except (DomainError, KeyError, TypeError, ValueError, AttributeError):
        return False
