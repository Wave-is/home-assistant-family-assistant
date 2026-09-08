"""Build a whole, isolated review copy; never write a Store or activate a runtime."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime

from ..const import LANGUAGES
from ..domain import alarms
from ..domain.context import Context
from ..domain.engine import Engine, new_state
from ..domain.shadow import SCHEMA, validate
from ..domain.validation import DomainError, timestamp
from .conversion import ConversionError, build_conversion_review
from .preflight import _bounded_json, _text
from .review import LegacyReview

_TASK_ID = re.compile(r"T[0-9]{6,12}")


class ShadowError(ValueError):
    """Fixed codes only; target/source contents are never error text."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _empty_target(target):
    if type(target) is not dict or not _bounded_json(target):
        raise ShadowError("shadow_target_invalid")
    try:
        members, settings = target["members"], target["settings"]
        owner = members["owner"]
        if owner["role"] != "owner" or owner["active"] is not True:
            raise ShadowError("shadow_target_invalid")
        expected = new_state(
            owner["ha_user_id"],
            settings["name"],
            settings["language"],
            [],
            timezone=settings["timezone"],
        )
        for member in members.values():
            if (
                not _text(member.get("name"), 80)
                or member.get("language") not in LANGUAGES
                or set(member)
                - {"id", "name", "role", "language", "active", "revision", "aliases", "ha_user_id"}
                or type(member.get("aliases")) is not list
                or len(member["aliases"]) > 20
                or not all(_text(alias, 80) for alias in member["aliases"])
                or (member.get("ha_user_id") is not None and not _text(member["ha_user_id"], 128))
            ):
                raise ShadowError("shadow_target_invalid")
        identities = [
            member["ha_user_id"] for member in members.values() if member.get("ha_user_id")
        ]
        if len(set(identities)) != len(identities):
            raise ShadowError("shadow_target_invalid")
        expected["members"] = members
        if _encode(expected) != _encode(target):
            raise ShadowError("shadow_empty_target_required")
    except (KeyError, TypeError, AttributeError, DomainError):
        raise ShadowError("shadow_target_invalid") from None


@dataclass(frozen=True, repr=False)
class ShadowCandidate:
    _state: bytes = field(repr=False)
    _summary: bytes = field(repr=False)

    def __repr__(self):
        return "ShadowCandidate(private=True, activation_available=False)"

    def private_state(self):
        """Only for isolated owner-private storage; never diagnostics/model input."""
        return json.loads(self._state)

    def summary(self):
        return json.loads(self._summary)


def build_shadow_candidate(
    review: LegacyReview, target: dict, *, reviewer_policy: dict, prepared_at: datetime
) -> ShadowCandidate:
    """Reject any blocked record/policy difference; no partial module import."""
    _empty_target(target)
    if type(review) is not LegacyReview or not review.matches_members(target["members"]):
        raise ShadowError("review_changed")
    try:
        prepared = timestamp(prepared_at, "prepared_at")
        conversion = build_conversion_review(
            review,
            target["settings"]["timezone"],
            members=target["members"],
            reviewer_policy=reviewer_policy,
        )
    except DomainError:
        raise ShadowError("shadow_time_invalid") from None
    except ConversionError as error:
        raise ShadowError(str(error)) from None
    summary = conversion.summary()
    if summary["blocked_records_count"]:
        raise ShadowError("shadow_complete_conversion_required")
    authority = summary["reviewer_authority"]
    if authority.get("mode") != "reviewer_set_review":
        raise ShadowError("shadow_reviewer_policy_required")
    if authority["changed_tasks_count"]:
        raise ShadowError("shadow_reviewer_decision_required")
    state = deepcopy(target)
    private = conversion.private_data()
    plans, id_map = (
        private["plans"],
        {name: {} for name in ("tasks", "shopping", "court", "alarms")},
    )
    # Keep task/reminder IDs recognizable. Shopping moves into its own namespace;
    # the exact old/new mapping remains in the owner-private migration archive.
    source_ledger = review.private_data()[0]
    source_ledger = source_ledger.get("ledger", source_ledger)
    if any(not _TASK_ID.fullmatch(key) for key in source_ledger["tasks"]):
        raise ShadowError("shadow_task_identifier_unsupported")
    state["sequences"]["T"] = max(
        [source_ledger.get("next_task_sequence", 1) - 1]
        + [int(key[1:]) for key in source_ledger["tasks"]]
    )
    state["sequences"]["M"] = max(
        [0] + [int(key[1:]) for key in state["members"] if re.fullmatch(r"M[0-9]{6,12}", key)]
    )
    for bucket in ("tasks", "shopping", "court"):
        for number, proposal in enumerate(plans[bucket]["proposals"], 1):
            source = proposal["source_event" if bucket == "court" else "source_task"]
            identifier = (
                source
                if bucket == "tasks"
                else f"{'S' if bucket == 'shopping' else 'C'}{number:06}"
            )
            if source in id_map[bucket] or identifier in state[bucket]:
                raise ShadowError("shadow_duplicate_identifier")
            id_map[bucket][source] = identifier
            state[bucket][identifier] = {
                **proposal["record"],
                "id": identifier,
                "revision": 1,
                # This is the target copy's construction time, not an old user action.
                "updated_at": prepared.isoformat(),
            }
        if bucket != "tasks":
            state["sequences"]["S" if bucket == "shopping" else "C"] = len(state[bucket])
    ctx = Context(state, state["members"]["owner"], prepared, "legacy-shadow-construction")
    for proposal in plans["alarms"]["proposals"]:
        record = alarms.handle(ctx, "save", deepcopy(proposal["payload"]))
        id_map["alarms"].setdefault(proposal["source_member"], {})[proposal["period"]] = record[
            "id"
        ]
    for balance in plans["court"]["balances"]:
        member = balance["target_binding"]["member_id"]
        if (
            sum(row["points"] for row in state["court"].values() if row["member"] == member)
            != balance["balance"]
        ):
            raise ShadowError("shadow_balance_mismatch")
    state["schema_version"] = SCHEMA
    state["migration_shadow"] = {
        "version": 1,
        "mode": "read_only",
        "source_fingerprint": review.summary()["fingerprint"],
        "conversion_fingerprint": summary["fingerprint"],
    }
    state["migration_archive"] = {
        "archive": private["archive"],
        "reviewer_authority": private["reviewer_authority"],
        "id_map": id_map,
        "prepared_at": prepared.isoformat(),
        "target_fingerprint": hashlib.sha256(_encode(target)).hexdigest(),
    }
    validate(state)

    # Exercise the actual domain projection contract without persistence or workers.
    async def forbidden_persist(_state):
        raise ShadowError("shadow_unexpected_write")

    Engine(state, forbidden_persist).view("owner", now=prepared)
    encoded = _encode(state)
    return ShadowCandidate(
        encoded,
        _encode(
            {
                "mode": "read_only_shadow",
                "fingerprint": hashlib.sha256(encoded).hexdigest(),
                "conversion_fingerprint": summary["fingerprint"],
                "counts": {
                    key: len(state[key])
                    for key in ("members", "tasks", "shopping", "court", "alarms")
                },
                "coherence_verified": False,
                "activation_available": False,
            }
        ),
    )
