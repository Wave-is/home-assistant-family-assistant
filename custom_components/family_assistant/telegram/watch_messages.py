"""Private parent inventory alerts rendered from current authorized observations."""

from ..network.admission_inventory import classify
from ..network.watch import current
from ..notifications import DeliveryError
from .admission import COPY as ADMISSION_COPY

COPY = {
    "en": "New unreviewed device observations since your baseline: {count}.",
    "ru": "Новые непроверенные устройства после сохранения исходного списка: {count}.",
    "uk": "Нові неперевірені пристрої після збереження початкового списку: {count}.",
}

COMMAND_COPY = {
    "en": {
        "on": (
            "Private new-device alerts are enabled. Existing observations form the baseline "
            "and are not announced. This does not change network access."
        ),
        "off": "Your private new-device alerts are disabled. Network access was not changed.",
        "help": "\n/network_alerts on or off — personal new-device alerts (private chat)",
    },
    "ru": {
        "on": (
            "Личные уведомления о новых устройствах включены. Уже наблюдаемые устройства "
            "входят в исходный список и не вызывают оповещений. Доступ к сети не изменён."
        ),
        "off": "Ваши личные уведомления о новых устройствах отключены. Доступ к сети не изменён.",
        "help": "\n/network_alerts on или off — личные уведомления о новых устройствах (в личке)",
    },
    "uk": {
        "on": (
            "Особисті сповіщення про нові пристрої ввімкнено. Уже спостережені пристрої "
            "входять до початкового списку та не викликають сповіщень. Доступ до мережі не змінено."
        ),
        "off": "Ваші особисті сповіщення про нові пристрої вимкнено. Доступ до мережі не змінено.",
        "help": (
            "\n/network_alerts on або off — особисті сповіщення про нові пристрої "
            "(у приватному чаті)"
        ),
    },
}


def targets(state, event):
    if not current(state, event):
        return []
    member = state["members"][event["recipient"]]
    return [{"channel": "telegram", "id": member["telegram_id"], "language": member["language"]}]


def render(state, event, target, now):
    allowed = targets(state, event)
    if (
        not current(state, event, now)
        or not allowed
        or any(target.get(key) != allowed[0][key] for key in ("channel", "id", "language"))
    ):
        raise DeliveryError("delivery_revoked")
    language = target.get("language", "en")
    labels = ADMISSION_COPY.get(language, ADMISSION_COPY["en"])
    inventory = classify(state["network"], now)
    rows = [
        row
        for row in inventory["devices"]
        if row["mac"] in event["data"]["macs"] and row["status"] == "unreviewed"
    ]
    lines = [COPY.get(language, COPY["en"]).format(count=len(rows)), inventory["observed_at"]]
    lines += [
        f"• {(row['candidate_name'] or labels['unknown'])[:60]} · {row['mac']} · "
        + ", ".join(row["addresses"][:2])
        for row in rows[:10]
    ]
    lines += [labels["more"].format(shown=min(10, len(rows)), count=len(rows)), labels["notice"]]
    return {"chat_id": target["id"], "text": "\n".join(lines)}
