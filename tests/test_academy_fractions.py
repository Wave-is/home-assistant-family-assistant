"""Synthetic tests for generated fraction tasks and the lesson plan."""

from fractions import Fraction

import pytest

from custom_components.family_assistant.academy.fractions import (
    MAX_SEED,
    TEMPLATES,
    generate,
    lesson,
)


@pytest.mark.parametrize("level", [1, 2, 3])
@pytest.mark.parametrize("template", TEMPLATES)
def test_generated_tasks(template, level):
    for seed in [*range(500), MAX_SEED]:
        task = generate(template, seed, level)
        assert task == generate(template, seed, level)
        assert task.check(str(task.expected)).status == "correct"
        assert task.check(str(task.expected + 1)).status == "incorrect"
        assert task.check("1/0").status == "invalid"
        n, d, *tail = task.parameters
        assert 0 < n < d
        if template == "read_bar":
            assert task.expected == Fraction(n, d)
        elif template == "equivalent":
            k, = tail
            assert Fraction(task.expected, d * k) == Fraction(n, d)
        elif template == "add":
            m, e = tail
            assert 0 < m < e
            assert (d == e) == (level == 1)
            assert task.expected == Fraction(n * e + m * d, d * e)
        else:
            total, = tail
            assert total % d == 0
            assert task.expected == n * (total // d)
        assert not {"expected", "solution", "hints"} & task.public().keys()
        assert task.public(assessment=True)["hint_count"] == 0


@pytest.mark.parametrize("level", [1, 2, 3])
def test_lesson(level):
    for seed in range(100):
        practice, exit_tasks = lesson(seed, level)
        assert len(practice) == 4 and len(exit_tasks) == 3
        all_tasks = practice + exit_tasks
        assert len({t.task_id for t in all_tasks}) == 7
        assert len({(t.template, t.parameters) for t in all_tasks}) == 7
        assert {t.template for t in exit_tasks} == set(TEMPLATES[1:])


@pytest.mark.parametrize("seed", [-1, MAX_SEED + 1, True, 1.0, "1"])
def test_invalid_seed(seed):
    with pytest.raises(ValueError):
        generate("add", seed)


@pytest.mark.parametrize("level", [0, 4, True, "2"])
def test_invalid_level(level):
    with pytest.raises(ValueError):
        generate("add", 0, level)


def test_invalid_template_and_lesson_bounds():
    with pytest.raises(ValueError):
        generate("unknown", 0)
    with pytest.raises(ValueError):
        lesson(MAX_SEED)
