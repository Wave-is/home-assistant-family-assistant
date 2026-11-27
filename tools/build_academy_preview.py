"""Build an offline, non-production demonstration with embedded answer keys."""

import argparse
import json
from pathlib import Path

from custom_components.family_assistant.academy.fractions import Task, lesson


def preview_task(task: Task) -> dict:
    return task.public() | {
        "expected": [task.expected.numerator, task.expected.denominator],
        "hints": list(task.hints),
        "solution": task.solution,
    }


def build(seed: int, level: int) -> str:
    practice, exit_tasks = lesson(seed, level)
    payload = {"practice": list(map(preview_task, practice)),
               "exit": list(map(preview_task, exit_tasks))}
    template = Path(__file__).with_name("academy_fractions_preview.html").read_text(encoding="utf-8")
    return template.replace("__ACADEMY_DATA__", json.dumps(payload).replace("<", "\\u003c"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--level", type=int, default=2)
    args = parser.parse_args()
    args.output.write_text(build(args.seed, args.level), encoding="utf-8")
