"""Keep every integration interval on HA's loop; native timer tests are separate."""

import ast
from pathlib import Path

import pytest


def lexical_functions(scope):
    pending = list(scope.body)
    while pending:
        node = pending.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node
        elif not isinstance(node, ast.ClassDef):
            # A try/if/with body is not a new Python lexical scope.
            pending[0:0] = list(ast.iter_child_nodes(node))


def interval_violations(source):
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    timers, callbacks = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                if (
                    node.module == "homeassistant.helpers.event"
                    and name.name == "async_track_time_interval"
                ):
                    timers.add(name.asname or name.name)
                if node.module == "homeassistant.core" and name.name == "callback":
                    callbacks.add(name.asname or name.name)
    problems, count = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_timer = (
            isinstance(node.func, ast.Name)
            and node.func.id in timers
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_track_time_interval"
        )
        if not is_timer:
            continue
        count += 1
        argument = (
            node.args[1]
            if len(node.args) > 1
            else next((item.value for item in node.keywords if item.arg == "action"), None)
        )
        name = None
        method = False
        if isinstance(argument, ast.Name):
            name = argument.id
        elif (
            isinstance(argument, ast.Attribute)
            and isinstance(argument.value, ast.Name)
            and argument.value.id in {"self", "cls"}
        ):
            name, method = argument.attr, True
        target = None
        scope = parents.get(node)
        while scope is not None:
            eligible = (
                isinstance(scope, ast.ClassDef)
                if method
                else isinstance(
                    scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
            )
            if eligible:
                matches = [item for item in lexical_functions(scope) if item.name == name]
                if matches:
                    target = matches[-1]
                    break
                if method:
                    break
            scope = parents.get(scope)
        loop_safe = isinstance(target, ast.AsyncFunctionDef) or (
            isinstance(target, ast.FunctionDef)
            and any(
                isinstance(decorator, ast.Name) and decorator.id in callbacks
                for decorator in target.decorator_list
            )
        )
        if not loop_safe:
            problems.append((node.lineno, ast.unparse(argument) if argument else "missing action"))
    return count, problems


def test_every_production_interval_has_an_explicit_loop_safe_callable():
    package = Path(__file__).resolve().parents[1] / "custom_components" / "family_assistant"
    total, problems = 0, []
    for path in package.rglob("*.py"):
        count, invalid = interval_violations(path.read_text(encoding="utf-8"))
        total += count
        problems.extend((str(path.relative_to(package)), *row) for row in invalid)
    assert total >= 6, "The guard must examine the actual timer registration sites."
    assert not problems, (
        "HA dispatches plain synchronous jobs in an executor; use an async interval wrapper "
        "or an explicit homeassistant.core.callback, then prove periodic native dispatch.",
        problems,
    )


@pytest.mark.parametrize(
    "definition,safe",
    [
        ("def request(self, now): pass", False),
        ("async def request(self, now): pass", True),
        ("@on_loop\n def request(self, now): pass", True),
    ],
)
def test_guard_resolves_bound_method_and_real_callback_alias(definition, safe):
    source = (
        "from homeassistant.helpers.event import async_track_time_interval as every\n"
        "from homeassistant.core import callback as on_loop\n"
        "class Other:\n async def request(self, now): pass\n"
        "class Worker:\n def start(self): every(self.hass, self.request, interval)\n "
        + definition
        + "\n"
    )
    count, invalid = interval_violations(source)
    assert count == 1 and bool(invalid) != safe


def test_guard_handles_nested_coroutine_and_rejects_unresolved_or_plain_job():
    for definition, safe in [("async def tick(now): pass", True), ("def tick(now): pass", False)]:
        source = (
            "from homeassistant.helpers.event import async_track_time_interval\n"
            "async def setup(hass):\n " + definition + "\n"
            " async_track_time_interval(hass, action=tick, interval=interval)\n"
        )
        count, invalid = interval_violations(source)
        assert count == 1 and bool(invalid) != safe
    count, invalid = interval_violations(
        "from homeassistant.helpers.event import async_track_time_interval\n"
        "async_track_time_interval(hass, unknown, interval)"
    )
    assert count == 1 and invalid


def test_try_if_blocks_do_not_hide_the_actual_lexical_coroutine():
    count, invalid = interval_violations(
        "from homeassistant.helpers.event import async_track_time_interval\n"
        "async def setup(hass):\n"
        " try:\n"
        "  if enabled:\n"
        "   async def tick(now): pass\n"
        "  async_track_time_interval(hass, tick, interval)\n"
        " finally: pass\n"
    )
    assert count == 1 and not invalid
