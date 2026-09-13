"""Deny-by-default CLI tool gate. Invoked by AGY, never by a model tool.

Profiles alone are NOT a permission boundary on CLI 1.2: its init event still
advertises the full tool set. This hook denies every operation except an exact
search query or fresh image generation. No file, terminal, browser, MCP, timer,
subagent, knowledge or communication tools are granted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID


def decision(payload, mode, query_hash=""):
    call = payload.get("toolCall", {})
    name, args = call.get("name"), call.get("args", {})
    if not isinstance(args, dict):
        return False
    if name == "finish":
        # CLI completion has no external effect. Structured answers are validated
        # independently by the gateway, not trusted merely because of this tool.
        return len(json.dumps(args)) <= 200_000
    if mode == "search" and name == "search_web":
        query = args.get("query")
        return (
            isinstance(query, str)
            and len(query) <= 300
            and hashlib.sha256(query.encode()).hexdigest() == query_hash
            and not args.get("domain")
        )
    if mode == "image" and name == "generate_image":
        return (
            not args.get("ImagePaths")
            and args.get("ImageName") == "family_result"
            and isinstance(args.get("Prompt"), str)
            and len(args["Prompt"]) <= 4000
        )
    return False


def _artifact(payload):
    """Only the current CLI-generated conversation artifact directory."""
    identifier = payload.get("conversationId", "")
    if str(UUID(identifier)) != identifier:
        raise ValueError("invalid_conversation")
    expected = Path.home() / ".gemini" / "antigravity-cli" / "brain" / identifier
    actual = Path(payload.get("artifactDirectoryPath", ""))
    if actual.resolve() != expected.resolve() or actual.is_symlink():
        raise ValueError("invalid_artifact_root")
    return actual


def main():
    result = {"decision": "deny", "reason": "Family gateway: tool not permitted."}
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("input_limit")
        payload = json.loads(raw)
        job = Path(os.environ["AGY_GATEWAY_JOB"])
        mode = os.environ["AGY_GATEWAY_MODE"]
        if sys.argv[1] == "pre":
            permitted = decision(payload, mode, os.environ.get("AGY_GATEWAY_QUERY_HASH", ""))
            result["decision"] = "allow" if permitted else "deny"
            # Counts-only execution proof, no tool arguments or prompt logging.
            with (job / "gate_events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {"name": payload.get("toolCall", {}).get("name"), "allowed": permitted}
                    )
                    + "\n"
                )
        elif sys.argv[1] == "post":
            if decision(payload, mode, os.environ.get("AGY_GATEWAY_QUERY_HASH", "")):
                if mode == "image":
                    from PIL import Image

                    artifact = _artifact(payload)
                    for path in artifact.iterdir():
                        if not re.fullmatch(
                            r"family_result(?:_[0-9]+)?\.(png|jpg|jpeg|webp)", path.name
                        ):
                            continue
                        if (
                            path.is_symlink()
                            or not path.is_file()
                            or not 0 < path.stat().st_size <= 6_000_000
                        ):
                            continue
                        with Image.open(path) as image:
                            if (
                                image.format not in {"PNG", "JPEG", "WEBP"}
                                or image.width * image.height > 16_777_216
                            ):
                                continue
                            image.verify()
                        (job / "image.png").write_bytes(path.read_bytes())
                elif mode == "search":
                    # This is the trusted tool envelope, never assistant prose.
                    (job / "search_evidence.json").write_text(json.dumps(payload), encoding="utf-8")
            result = {}
    except Exception:
        # Missing/malformed context cannot turn a denied tool into an approval.
        result = {"decision": "deny", "reason": "Family gateway: invalid tool context."}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
