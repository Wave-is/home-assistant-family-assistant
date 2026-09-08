"""Parent-private equipment documents. No task, notification or equipment effects."""

from __future__ import annotations

from copy import deepcopy

from ..const import PRIVILEGED
from . import maintenance
from .context import Context
from .validation import DomainError, fields, revision, text, timestamp

PURPOSE = "equipment_document"
MAX_DOCUMENTS = 5000
MAX_ASSET_DOCUMENTS = 10
KINDS = frozenset({"manual", "warranty", "receipt", "other"})


def _actor(state: dict, actor: dict) -> dict:
    current = state.get("members", {}).get(actor.get("id")) if isinstance(actor, dict) else None
    if (
        not isinstance(current, dict)
        or current.get("active") is not True
        or current.get("role") not in PRIVILEGED
        or current.get("role") != actor.get("role")
        or revision(current.get("revision")) != revision(actor.get("revision"))
    ):
        raise DomainError("forbidden")
    maintenance._require_module(state)
    return current


def _asset(state: dict, actor: dict, asset_id) -> dict:
    _actor(state, actor)
    asset_id = text(asset_id, "asset_id", 80)
    asset = maintenance._bucket(state, "assets").get(asset_id)
    if (
        not isinstance(asset, dict)
        or asset.get("id") != asset_id
        or asset.get("status") not in {"active", "retired"}
    ):
        raise DomainError("forbidden")
    revision(asset.get("revision"))
    return asset


def _documents(state: dict) -> dict:
    return maintenance._bucket(state, "documents")


def upload_target(state: dict, actor: dict, asset_id, asset_revision) -> tuple[dict, dict]:
    asset = _asset(state, actor, asset_id)
    if asset["revision"] != revision(asset_revision):
        raise DomainError("conflict")
    documents = _documents(state)
    if (
        len(documents) >= MAX_DOCUMENTS
        or sum(
            isinstance(row, dict)
            and row.get("asset_id") == asset_id
            and row.get("status") == "attached"
            for row in documents.values()
        )
        >= MAX_ASSET_DOCUMENTS
    ):
        raise DomainError("quota_exceeded")
    return asset, {"asset_id": asset["id"], "asset_revision": asset["revision"]}


def attached_reference(state: dict, actor: dict, media_record: dict) -> bool:
    scope = media_record.get("scope")
    if (
        media_record.get("purpose") != PURPOSE
        or not isinstance(scope, dict)
        or set(scope) != {"kind", "asset_id", "document_id"}
        or scope.get("kind") != PURPOSE
    ):
        return False
    try:
        _asset(state, actor, scope["asset_id"])
        document = _documents(state).get(scope["document_id"])
        if not isinstance(document, dict):
            return False
        revision(document.get("revision"))
    except DomainError:
        return False
    return (
        document.get("id") == scope["document_id"]
        and document.get("asset_id") == scope["asset_id"]
        and document.get("media_id") == media_record.get("id")
        and document.get("status") == "attached"
    )


def view(state: dict, actor: dict) -> list[dict]:
    from . import media

    _actor(state, actor)
    result = []
    for document in _documents(state).values():
        if not isinstance(document, dict) or document.get("status") not in {"attached", "deleted"}:
            continue
        row = deepcopy(document)
        row.pop("media_id", None)
        if document["status"] == "attached":
            try:
                row["attachment"] = media.read_metadata(
                    state, actor, document.get("media_id"), None
                )
            except DomainError:
                row["attachment"] = None
        result.append(row)
    return result


def handle(ctx: Context, action: str, payload: dict) -> dict:
    from . import media

    common = {"id", "revision", "actor_member_revision", "media"}
    extra = {"title", "kind", "note"} if action == "document_attach" else {"document", "reason"}
    if action not in {"document_attach", "document_purge"}:
        raise DomainError("unknown_action")
    fields(payload, common | extra, common | extra)
    actor = _actor(ctx.state, ctx.actor)
    if revision(payload["actor_member_revision"]) != actor["revision"]:
        raise DomainError("conflict")
    asset = _asset(ctx.state, actor, payload["id"])
    if revision(payload["revision"]) != asset["revision"]:
        raise DomainError("conflict")
    reference = payload["media"]
    if not isinstance(reference, dict):
        raise DomainError("invalid_field", "media")
    fields(reference, {"id", "revision"}, {"id", "revision"})
    record = media._record(ctx.state, reference["id"])
    media._blob_key(record)
    if record["revision"] != revision(reference["revision"]):
        raise DomainError("conflict")
    media._ensure_advance(record)
    if action == "document_attach":
        _, target = upload_target(ctx.state, actor, asset["id"], asset["revision"])
        title = text(payload["title"], "title", 160)
        kind = payload["kind"]
        if not isinstance(kind, str) or kind not in KINDS:
            raise DomainError("invalid_field", "kind")
        note = maintenance._optional_text(payload["note"], "note", 1000)
        if record.get("purpose") != PURPOSE or record.get("status") != "available":
            raise DomainError("invalid_transition")
        if record.get("mime_type") not in media.mimes_for(PURPOSE):
            raise DomainError("invalid_field", "mime_type")
        _, current = media._reserved_authority(ctx.state, actor, record)
        if current != target:
            raise DomainError("conflict")
        if timestamp(ctx.now, "now") >= timestamp(record.get("expires_at"), "expires_at"):
            raise DomainError("invalid_transition")
        document = {
            "id": ctx.identifier("MD"),
            "revision": 1,
            "asset_id": asset["id"],
            "title": title,
            "kind": kind,
            "note": note,
            "media_id": record["id"],
            "status": "attached",
            "attached_by": actor["id"],
            "attached_by_revision": actor["revision"],
            "attached_at": ctx.now.isoformat(),
        }
        maintenance._mutable_bucket(ctx, "documents")[document["id"]] = document
        record.update(
            status="attached",
            scope={"kind": PURPOSE, "asset_id": asset["id"], "document_id": document["id"]},
            expires_at=None,
        )
    else:
        if actor["role"] != "owner":
            raise DomainError("forbidden")
        doc_ref = payload["document"]
        if not isinstance(doc_ref, dict):
            raise DomainError("invalid_field", "document")
        fields(doc_ref, {"id", "revision"}, {"id", "revision"})
        document = maintenance._record(
            _documents(ctx.state), doc_ref["id"], doc_ref["revision"], for_update=True
        )
        if (
            document.get("asset_id") != asset["id"]
            or document.get("media_id") != record["id"]
            or record.get("status") != "attached"
            or not attached_reference(ctx.state, actor, record)
        ):
            raise DomainError("conflict")
        document.update(
            status="deleted",
            deleted_by=actor["id"],
            deleted_by_revision=actor["revision"],
            deleted_at=ctx.now.isoformat(),
            reason=text(payload["reason"], "reason", 500),
        )
        ctx.touch(document)
        record["status"] = "deleting"
    media._advance(ctx, record)
    # Appending a document must not change the equipment's revision and suspend
    # already reviewed recurring service rules that pin that revision.
    return {key: document[key] for key in ("id", "revision", "asset_id", "status")}


def authorize_replay(ctx: Context, action: str, payload: dict) -> None:
    from . import media

    actor = _actor(ctx.state, ctx.actor)
    if revision(payload.get("actor_member_revision")) != actor["revision"]:
        raise DomainError("conflict")
    asset = _asset(ctx.state, actor, payload.get("id"))
    if revision(payload.get("revision")) != asset["revision"]:
        raise DomainError("conflict")
    reference = payload.get("media")
    if not isinstance(reference, dict):
        raise DomainError("forbidden")
    if action == "document_attach":
        record = media._record(ctx.state, reference.get("id"))
        if record.get("status") != "attached" or not attached_reference(ctx.state, actor, record):
            raise DomainError("conflict")
        if record["scope"]["asset_id"] != asset["id"]:
            raise DomainError("conflict")
    elif action == "document_purge":
        doc_ref = payload.get("document")
        document = (
            _documents(ctx.state).get(doc_ref.get("id")) if isinstance(doc_ref, dict) else None
        )
        if (
            actor["role"] != "owner"
            or not isinstance(document, dict)
            or document.get("status") != "deleted"
            or document.get("asset_id") != asset["id"]
            or document.get("media_id") != reference.get("id")
            or document.get("deleted_by") != actor["id"]
            or document.get("deleted_by_revision") != actor["revision"]
            or revision(document.get("revision")) != revision(doc_ref.get("revision")) + 1
        ):
            raise DomainError("forbidden")
    else:
        raise DomainError("unknown_action")
