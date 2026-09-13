"""Subprocess execution and process-group lifecycle management for AGY CLI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from .events import error_code, events

logger = logging.getLogger(__name__)

PROFILES_SRC_DIR = Path(__file__).parent / ".agents" / "agents"


def hook_command():
    parts = [sys.executable, str(Path(__file__).with_name("hooks.py").resolve())]
    return subprocess.list2cmdline(parts) if sys.platform == "win32" else shlex.join(parts)


def install_service_policy(root: Path):
    """Only for an explicitly dedicated gateway container authentication volume."""
    if os.environ.get("AGY_DEDICATED_PROFILE") != "1":
        raise RuntimeError("dedicated_gateway_profile_required")
    root = root.resolve()
    cli = root / ".gemini" / "antigravity-cli"
    config = root / ".gemini" / "config"
    config.mkdir(parents=True, exist_ok=True)
    cli.mkdir(parents=True, exist_ok=True)
    command = hook_command()
    (config / "hooks.json").write_text(
        json.dumps(
            {
                "family-gateway": {
                    "PreToolUse": [
                        {"matcher": "*", "hooks": [{"command": command + " pre", "timeout": 5}]}
                    ],
                    "PostToolUse": [
                        {
                            "matcher": "search_web|generate_image",
                            "hooks": [{"command": command + " post", "timeout": 10}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    (cli / "settings.json").write_text(
        json.dumps(
            {
                "toolPermission": "request-review",
                "allowNonWorkspaceAccess": False,
                "permissions": {
                    "deny": [
                        "command(*)",
                        "unsandboxed(*)",
                        "read_file(*)",
                        "write_file(*)",
                        "execute_url(*)",
                        "mcp(*)",
                    ],
                    "allow": [],
                },
            }
        ),
        encoding="utf-8",
    )


class ProcessExecutionError(Exception):
    """Raised when the AGY CLI process fails."""

    def __init__(
        self, message: str, exit_code: int | None = None, *, code=None, image_quota_proven=False
    ):
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.image_quota_proven = image_quota_proven


class OutputLimitExceededError(ProcessExecutionError):
    """Raised when AGY CLI output exceeds memory/byte limits."""


def setup_job_runtime_directory(job_dir: Path) -> Path:
    """Prepare an isolated runtime cwd with explicit copied agent profiles.

    Antigravity CLI discovers customizations upwards from the runtime CWD.
    Copying explicit profile files ensures the job runtime discovers only
    authorized agent profiles and no parent/neighbor customizations.
    """
    job_agents_dir = job_dir / ".agents" / "agents"
    job_agents_dir.mkdir(parents=True, exist_ok=True)

    if PROFILES_SRC_DIR.is_dir():
        for profile in PROFILES_SRC_DIR.glob("*.md"):
            dest = job_agents_dir / profile.name
            shutil.copyfile(profile, dest)

    command = hook_command()
    hooks = {
        "family-gateway": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"command": command + " pre", "timeout": 5}]}
            ],
            "PostToolUse": [
                {
                    "matcher": "search_web|generate_image",
                    "hooks": [{"command": command + " post", "timeout": 10}],
                }
            ],
        }
    }
    (job_dir / ".agents" / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")

    return job_dir


def kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """Terminate the process group securely across Windows and POSIX."""
    if proc.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(  # noqa: S603 — fixed OS binary and numeric child PID, no shell.
                [
                    str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                    "/F",
                    "/T",
                    "/PID",
                    str(proc.pid),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
    except OSError:
        logger.debug("Process group already exited or could not be terminated")

    try:
        proc.kill()
    except ProcessLookupError:
        logger.debug("Child process already exited")


async def _read_bounded_stream(stream: asyncio.StreamReader | None, max_bytes: int) -> bytes:
    """Read stream in chunks up to max_bytes, raising if exceeded."""
    if stream is None:
        return b""
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise OutputLimitExceededError("Subprocess output exceeded bounded limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def run_agy_command(
    args: list[str],
    *,
    stdin_text: str | None = None,
    cwd: Path,
    timeout: int = 60,
    max_output_bytes: int = 8 * 1024 * 1024,
) -> str:
    """Execute AGY CLI in a strictly isolated process group with bounded output.

    - args: strictly a list of command arguments (no shell=True)
    - kill process group on timeout or cancellation
    - output bounded to max_output_bytes (default 8MB)
    - no prompts or raw stderr logged
    """
    setup_job_runtime_directory(cwd)

    # Clean environment without injecting shell or bypass flags
    clean_env = os.environ.copy()
    # Remove any dangerous bypass flags if present
    clean_env.pop("AGY_BYPASS_SANDBOX", None)
    clean_env.pop("AGY_ALLOW_SHELL", None)
    clean_env.pop("AGY_API_KEY", None)
    agent = args[args.index("--agent") + 1]
    mode = {"family-text": "chat", "family-search": "search", "family-image": "image"}[agent]
    clean_env["AGY_GATEWAY_JOB"] = str(cwd.resolve())
    clean_env["AGY_GATEWAY_MODE"] = mode
    if mode == "search":
        clean_env["AGY_GATEWAY_QUERY_HASH"] = hashlib.sha256(
            (stdin_text or "").encode()
        ).hexdigest()
        stdin_text = (
            "Call search_web exactly once with this exact query, without reformulating it: "
            + json.dumps(stdin_text)
        )
    # --print is the documented noninteractive mode. CLI has no --non-interactive.
    args = list(args)
    args.remove("--non-interactive")
    args.extend(["--new-project", "--print-timeout", f"{timeout}s", "--print", stdin_text or ""])
    stdin_text = None

    popen_kwargs: dict[str, object] = {
        "stdin": asyncio.subprocess.PIPE if stdin_text is not None else asyncio.subprocess.DEVNULL,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": str(cwd),
        "env": clean_env,
    }

    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    proc = await asyncio.create_subprocess_exec(*args, **popen_kwargs)

    try:
        async with asyncio.timeout(timeout):
            stdin_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
            if stdin_bytes and proc.stdin:
                proc.stdin.write(stdin_bytes)
                await proc.stdin.drain()
                proc.stdin.close()

            # Read stdout and stderr concurrently with bounding
            stdout_task = asyncio.create_task(_read_bounded_stream(proc.stdout, max_output_bytes))
            stderr_task = asyncio.create_task(_read_bounded_stream(proc.stderr, max_output_bytes))

            try:
                stdout_bytes, _stderr_bytes = await asyncio.gather(stdout_task, stderr_task)
                await proc.wait()
            except OutputLimitExceededError:
                kill_process_group(proc)
                await proc.wait()
                raise

        if proc.returncode != 0:
            logger.warning("AGY process exited with non-zero status %s", proc.returncode)
            decoded = stdout_bytes.decode("utf-8", errors="replace")
            code = error_code(decoded)
            image_steps = [
                value.get("step_update", {})
                for value in events(decoded)
                if value.get("event") == "step_update"
                and value.get("step_update", {}).get("tool_name") == "generate_image"
            ]
            image_quota = code == "quota_exceeded" and not image_steps
            if image_steps:
                last = image_steps[-1]
                detail = json.dumps(last.get("tool_info", {}).get("error", {})).lower()
                image_quota = (
                    last.get("state") == "ERROR"
                    and any(
                        word in detail
                        for word in ("resource_exhausted", "quota", "429", "rate limit")
                    )
                    and not any(step.get("state") == "DONE" for step in image_steps)
                )
            raise ProcessExecutionError(
                "Process execution failed",
                exit_code=proc.returncode,
                code=code,
                image_quota_proven=image_quota,
            )

        return stdout_bytes.decode("utf-8", errors="replace")

    except TimeoutError:
        logger.warning("AGY process execution timed out after %d seconds", timeout)
        kill_process_group(proc)
        try:
            await proc.wait()
        except ProcessLookupError:
            logger.debug("Timed-out child already exited")
        raise
    except asyncio.CancelledError:
        logger.info("AGY process execution cancelled; terminating process group")
        kill_process_group(proc)
        try:
            await proc.wait()
        except ProcessLookupError:
            logger.debug("Cancelled child already exited")
        raise
