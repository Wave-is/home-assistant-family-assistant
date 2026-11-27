"""Versioned, deterministic fraction tasks and the first lesson plan."""

from dataclasses import dataclass
from fractions import Fraction
from math import lcm

from .rational import RationalResult, check_rational

VERSION = 1
TEMPLATES = ("read_bar", "equivalent", "add", "part_of_whole")
MAX_SEED = 2**32 - 1


@dataclass(frozen=True, slots=True)
class Task:
    template: str
    seed: int
    level: int
    parameters: tuple[int, ...]
    prompt: str
    expected: Fraction
    hints: tuple[str, str]
    solution: str

    @property
    def task_id(self) -> str:
        return f"fractions:v{VERSION}:{self.template}:{self.level}:{self.seed}"

    def public(self, *, assessment: bool = False) -> dict:
        """No expected answer or solution in the learner projection."""
        return {
            "id": self.task_id,
            "template": self.template,
            "level": self.level,
            "parameters": list(self.parameters),
            "prompt": self.prompt,
            "hint_count": 0 if assessment else len(self.hints),
        }

    def check(self, answer: str) -> RationalResult:
        return check_rational(answer, self.expected)


def generate(template: str, seed: int, level: int = 1) -> Task:
    """Stable finite parameter space; v1 must not change after release."""
    if template not in TEMPLATES:
        raise ValueError("unknown template")
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError("seed out of range")
    if type(level) is not int or level not in (1, 2, 3):
        raise ValueError("level out of range")
    # Enumerate denominator/numerator combinations without runtime RNG.
    pairs = tuple((n, d) for d in range(2 + 2 * (level - 1), 7 + 2 * (level - 1))
                  for n in range(1, d))
    n, d = pairs[seed % len(pairs)]
    k = 2 + (seed // len(pairs)) % 4
    if template == "read_bar":
        return Task(template, seed, level, (n, d), "What fraction of the bar is filled?",
                    Fraction(n, d), ("Count equal parts.", "Put filled parts over all parts."),
                    f"{n} of {d} equal parts are filled: {n}/{d} = {Fraction(n, d)}.")
    if template == "equivalent":
        return Task(template, seed, level, (n, d, k),
                    f"Find the missing numerator: {n}/{d} = ?/{d*k}.", Fraction(n*k),
                    ("Both fractions must represent the same amount.",
                     f"Multiply both numerator and denominator by {k}."),
                    f"{n} × {k} = {n*k}; {d} × {k} = {d*k}.")
    if template == "add":
        e = d if level == 1 else d + (1 if level == 2 else 2)
        m = 1 + (seed // len(pairs)) % (e - 1)
        common = lcm(d, e)
        a, b = n * (common // d), m * (common // e)
        expected = Fraction(n, d) + Fraction(m, e)
        return Task(template, seed, level, (n, d, m, e), f"Calculate {n}/{d} + {m}/{e}.",
                    expected, ("Add pieces of the same size, not denominators.",
                               f"Use a common denominator of {common}."),
                    f"{a}/{common} + {b}/{common} = {a+b}/{common} = {expected}.")
    total = d * k
    return Task(template, seed, level, (n, d, total),
                f"A space station has {total} energy cells. {n}/{d} are charged. "
                "How many cells are charged?", Fraction(n*k),
                ("Find the value of one equal group first.",
                 f"Divide {total} by {d}, then multiply by {n}."),
                f"{total} ÷ {d} × {n} = {n*k} cells.")


def lesson(seed: int, level: int = 1) -> tuple[tuple[Task, ...], tuple[Task, ...]]:
    """Four guided tasks and three independent exit tasks with fresh operands."""
    if type(seed) is not int or not 0 <= seed <= MAX_SEED - 10:
        raise ValueError("lesson seed out of range")
    practice = tuple(generate(t, seed + i, level) for i, t in enumerate(TEMPLATES))
    exit_tasks = tuple(generate(t, seed + i + 1, level)
                       for i, t in enumerate(TEMPLATES[1:], start=1))
    return practice, exit_tasks
