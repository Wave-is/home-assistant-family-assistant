"""Additional immutable v1 fraction templates and exact mixed-number grading."""

import re
from fractions import Fraction
from math import lcm

from .fractions import TEMPLATES, Task, generate
from .rational import RationalResult

SKILLS = {
    "fraction_value": ("read_bar", "equivalent", "fraction_story"),
    "addition": ("add", "add_story"),
    "subtraction": ("subtract", "subtract_story"),
    "multiplication": ("multiply", "multiply_story"),
    "division": ("divide", "divide_story"),
    "mixed_numbers": ("mixed_to_improper", "improper_to_mixed", "mixed_story"),
}
PREREQUISITES = {
    "fraction_value": (), "addition": ("fraction_value",),
    "subtraction": ("addition",), "multiplication": ("fraction_value",),
    "division": ("multiplication",), "mixed_numbers": ("fraction_value",),
}
_MIXED = re.compile(r"([+-]?)([0-9]{1,12})[ \t]+([0-9]{1,12})\s*/\s*([0-9]{1,12})")


def extended_task(template: str, seed: int, level: int = 1) -> Task:
    if template in TEMPLATES:
        return generate(template, seed, level)
    if template not in {t for ts in SKILLS.values() for t in ts}:
        raise ValueError("unknown template")
    # Reuse the frozen v1 parameter sampler and its bounds.
    n, d, m, e = generate("add", seed, level).parameters
    a, b = Fraction(n, d), Fraction(m, e)
    if template == "fraction_story":
        return Task(template, seed, level, (n, d),
                    f"Of {d} station modules, {n} are active. What fraction is active?",
                    a, ("Count active modules.", "Put active over total."),
                    f"{n}/{d} = {a}.")
    if template in SKILLS["mixed_numbers"]:
        whole = 1 + (seed // 7) % (level + 2)
        value = whole + a
        mixed = f"{whole} {a.numerator}/{a.denominator}"
        improper = f"{whole*d+n}/{d}"
        if template == "mixed_to_improper":
            prompt = f"Write {whole} {n}/{d} as an improper fraction."
        elif template == "improper_to_mixed":
            prompt = f"Write {improper} as a mixed number (e.g. 2 1/3)."
        else:
            prompt = (f"A rover travels {improper} km. Write this distance as a mixed "
                      "number (e.g. 2 1/3), without units.")
        return Task(template, seed, level, (whole, n, d), prompt, value,
                    ("Separate whole units from the fractional part.",
                     "Use quotient and remainder, or multiply the whole by the denominator."),
                    f"{improper} = {mixed}.")
    op = template.removesuffix("_story")
    if op == "subtract" and a < b:
        n, d, m, e = m, e, n, d
        a, b = b, a
    if op == "add":
        expected, sign = a + b, "+"
        story = f"Two cables are {n}/{d} m and {m}/{e} m long. What is their total length in m?"
    elif op == "subtract":
        expected, sign = a - b, "−"
        story = f"A {n}/{d} m cable loses {m}/{e} m. How much remains in m?"
    elif op == "multiply":
        expected, sign = a * b, "×"
        story = f"A tank is {n}/{d} full. A rover uses {m}/{e} of that water. What fraction of a full tank is used?"
    else:
        expected, sign = a / b, "÷"
        story = f"A tank holds {n}/{d} L. One unit is {m}/{e} L. How many units (including partial units) are in the tank?"
    if op in ("add", "subtract"):
        common = lcm(d, e)
        hints = ("Use equal-sized parts.", f"Use a common denominator of {common}.")
        step = f"{n*(common//d)}/{common} {sign} {m*(common//e)}/{common}"
    elif op == "multiply":
        hints = ("Multiply the fractions, then simplify.", "Multiply numerators and denominators separately.")
        step = f"{n*m}/{d*e}"
    else:
        hints = ("How many groups of the second fraction fit in the first?", "Multiply by the reciprocal of the second fraction.")
        step = f"{n}/{d} × {e}/{m} = {n*e}/{d*m}"
    expression = f"{n}/{d} {sign} {m}/{e}"
    prompt = story + " Enter a number without units." if template.endswith("_story") else f"Calculate {expression}."
    return Task(template, seed, level, (n, d, m, e), prompt, expected, hints,
                f"{expression} = {step} = {expected}.")


def grade(task: Task, answer: str) -> RationalResult:
    if not isinstance(answer, str) or len(answer) > 80:
        return RationalResult("invalid", "invalid_input")
    value = answer.strip().replace("−", "-")
    match = _MIXED.fullmatch(value)
    mixed_required = task.template in ("improper_to_mixed", "mixed_story")
    if match:
        sign, whole, numerator, denominator = match.groups()
        w, n, d = int(whole), int(numerator), int(denominator)
        if not (w > 0 and 0 < n < d):
            return RationalResult("invalid", "invalid_mixed_number")
        parsed = (w + Fraction(n, d)) * (-1 if sign == "-" else 1)
        # Avoid re-parsing potentially large products; compare exactly instead.
        status = "correct" if parsed == task.expected else "incorrect"
        code = "equivalent_value" if status == "correct" else "different_value"
        if task.template == "mixed_to_improper" and status == "correct":
            return RationalResult("incorrect", "improper_fraction_required", str(parsed))
        return RationalResult(status, code, str(parsed))
    result = task.check(answer)
    if result.status == "correct" and mixed_required:
        return RationalResult("incorrect", "mixed_number_required", result.normalized)
    if result.status == "correct" and task.template == "mixed_to_improper" and "/" not in value:
        return RationalResult("incorrect", "improper_fraction_required", result.normalized)
    return result


def fingerprint(skill: str, task: Task) -> str:
    """Ignore seed, presentation and equivalent operand notation in evidence."""
    p = task.parameters
    if skill == "fraction_value":
        values = (Fraction(p[0], p[1]),)
    elif skill == "mixed_numbers":
        values = (p[0] + Fraction(p[1], p[2]),)
    else:
        values = (Fraction(p[0], p[1]), Fraction(p[2], p[3]))
        if skill in ("addition", "multiplication"):
            values = tuple(sorted(values))
    return skill + ":" + ":".join(map(str, values))
