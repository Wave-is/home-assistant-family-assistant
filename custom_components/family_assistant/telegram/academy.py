"""Private deterministic Academy commands; never forward them to a model."""

from ..domain import academy, shadow
from ..domain.validation import DomainError
from .context import PersonalReply


class AcademyReply(PersonalReply):
    """Bind a queued private reply to its exact authorized projection."""

    def __new__(cls, value, scope):
        instance = super().__new__(cls, value)
        instance.academy_scope = scope
        return instance


def reply_current(state, data, now):
    try:
        actor = state["members"][data["actor"]]
        result = academy.project(state, actor, now)
        return data["academy_context"] == _scope(result)
    except (DomainError, KeyError, TypeError, ValueError):
        return False


def _scope(result):
    return [[row["id"], row["revision"], row["bound"],
             row["question"]["topic"] if row["question"] else None]
            for row in result["assignments"]]


async def route(engine, actor, content, operation_id, now, *, private, language):
    command, _, tail = content.strip().partition(" ")
    command = command.split("@", 1)[0].casefold()
    if command not in {"/academy", "/academyanswer"}:
        return None
    if not private:
        return "Academy: private chat only / Лише приватний чат"
    state = engine.snapshot()
    if shadow.validate(state):
        raise DomainError("migration_shadow_read_only")
    if command == "/academyanswer":
        parts = [part.strip() for part in tail.split("|")]
        if len(parts) != 4 or not parts[1].isdigit() or len(parts[1]) > 16:
            raise DomainError("invalid_field")
        await engine.execute(actor, "academy.answer",
                             {"id": parts[0], "revision": int(parts[1]), "topic": parts[2],
                              "answer": parts[3]}, operation_id, now)
        state = engine.snapshot()
    result = academy.project(state, state["members"][actor], now)
    lines = ["🎓 Academy"]
    for row in result["assignments"]:
        lines.append(f"{row['id']} · {row['grade']} · {row['mastered']}/{len(row['topics'])}")
        if not row["active"]:
            lines.append("Archived / Архів")
        if row["history"]:
            lines.append("✓" if row["history"][-1]["correct"] else "↻")
        if question := row["question"]:
            lines.extend([question["title"], question["lesson"], question["prompt"],
                          f"/academyanswer {row['id']} | {row['revision']} | {question['topic']} | …"])
        if len(lines) > 22:
            break
    if len(lines) == 1:
        lines.append("No assignments / Немає призначень")
    return AcademyReply("\n".join(lines)[:3500], _scope(result))
