"""Transaction-scoped actor and helpers. Roles never come from command payloads."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from ..const import PRIVILEGED
from .validation import DomainError, text
from .validation import revision as validate_revision

_UNSPECIFIED_REVISION = object()


@dataclass
class Context:
    state: dict
    actor: dict
    now: datetime
    operation_id: str

    @property
    def privileged(self) -> bool:
        return self.actor["role"] in PRIVILEGED

    @property
    def actor_id(self) -> str:
        return self.actor["id"]

    def require_parent(self) -> None:
        if not self.privileged:
            raise DomainError("forbidden")

    def member(self, member_id: str) -> dict:
        member_id = text(member_id, "member", 80)
        member = self.state["members"].get(member_id)
        if member is None or not member.get("active", True):
            raise DomainError("unknown_member")
        return member

    def identifier(self, prefix: str) -> str:
        sequence = self.state["sequences"].get(prefix, 0) + 1
        self.state["sequences"][prefix] = sequence
        return f"{prefix}{sequence:06}"

    def record(self, bucket: str, record_id: str, revision=_UNSPECIFIED_REVISION) -> dict:
        record_id = text(record_id, "id", 80)
        result = self.state[bucket].get(record_id)
        if result is None:
            raise DomainError("not_found")
        if (
            revision is not _UNSPECIFIED_REVISION
            and validate_revision(revision) != result["revision"]
        ):
            raise DomainError("conflict")
        return result

    def touch(self, record: dict) -> dict:
        record["revision"] = record.get("revision", 0) + 1
        record["updated_at"] = self.now.isoformat()
        return record

    def notify(self, recipient: str, key: str, data: dict) -> str:
        suffix = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
        notification_id = f"{self.operation_id}:{recipient}:{key}:{suffix}"
        self.state["outbox"].setdefault(
            notification_id,
            {
                "id": notification_id,
                "recipient": recipient,
                "key": key,
                "data": data,
                "created_at": self.now.isoformat(),
                "state": "pending",
                "attempts": 0,
            },
        )
        return notification_id
