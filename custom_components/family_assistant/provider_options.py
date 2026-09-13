"""Fence ConfigEntry-only provider forms to the exact owner and displayed settings."""

from copy import deepcopy
from functools import wraps

from .domain.settings import current_revision
from .domain.validation import DomainError


async def _scope(flow):
    from .command_scope import capture
    from .flow_identity import user_id

    runtime, actor = flow._authorized_runtime()
    scope = await capture(flow.hass, flow.config_entry.entry_id, user_id(flow))
    await scope.check()
    current_runtime, current_actor = flow._authorized_runtime()
    if runtime is not current_runtime or scope.runtime is not runtime or actor != current_actor:
        raise DomainError("conflict")
    return (
        scope,
        deepcopy(dict(flow.config_entry.options)),
        current_revision(runtime.engine.snapshot()),
    )


def _same(left, right):
    if right is None:
        return False
    a, b = left[0], right[0]
    return (
        a.runtime is b.runtime
        and a.engine is b.engine
        and a.user_id == b.user_id
        and a.actor == b.actor
        and a.actor_revision == b.actor_revision
        and left[1:] == right[1:]
    )


def guarded_provider_step(method=None, *, member_attribute=None):
    """Only for steps returning Options, never for steps committing Engine mutations.

    HA applies a create_entry result after the step returns. The final check can
    therefore reject either a stale write or a private error form before either
    becomes externally visible. Scope stays server-side; never include it in
    a flow result, projection or log.
    """

    if method is None:
        return lambda selected: guarded_provider_step(selected, member_attribute=member_attribute)

    @wraps(method)
    async def guarded(flow, user_input=None):
        key = "_displayed_" + method.__name__
        try:
            before = await _scope(flow)
            target = getattr(flow, member_attribute, None) if member_attribute else None
            member = deepcopy(before[0].engine.snapshot()["members"].get(target))
            expected = getattr(flow, key, None)
            if user_input is not None:
                if not _same(before, expected):
                    raise DomainError("conflict")
                await expected[0].check()
            result = await method(flow, user_input)
            await before[0].check()
            after = await _scope(flow)
            if not _same(before, after) or (
                target is not None and after[0].engine.snapshot()["members"].get(target) != member
            ):
                raise DomainError("conflict")
            setattr(flow, key, after if result.get("type") == "form" else None)
            return result
        except DomainError as error:
            setattr(flow, key, None)
            return flow.async_abort(reason=error.code)

    return guarded
