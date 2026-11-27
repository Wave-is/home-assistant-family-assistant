"""Private deterministic Academy commands; never forward them to a model."""

from ..domain import academy
from ..domain.validation import DomainError
from .context import PersonalReply


async def route(engine, actor, content, operation_id, now, *, private, language):
    command, _, tail = content.strip().partition(" ")
    command = command.split("@", 1)[0].casefold()
    if command not in {"/academy", "/academyanswer"}:
        return None
    if not private:
        return PersonalReply("Academy: private chat only / Лише приватний чат")
    if engine.shadow_mode:
        raise DomainError("migration_shadow_read_only")
    state = engine.snapshot()
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
    return PersonalReply("\n".join(lines)[:3500])
