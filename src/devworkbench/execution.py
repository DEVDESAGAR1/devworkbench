"""Common secure command execution layer for DevWorkBench.

Provides execution isolation, UTF-8 safety, timeout enforcement, secret redaction,
and structured command execution tracking.
"""

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from devworkbench.models import CommandExecution

# Common regex patterns to identify sensitive parameters and values
SECRET_PATTERNS = [
    re.compile(r"(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token|auth[_-]?token)=([^\s]+)", re.IGNORECASE),
    re.compile(r"(--password|--token|--secret|--api-key|--access-key)\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"(AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|GITHUB_TOKEN|GITLAB_TOKEN|VAULT_TOKEN)=([^\s]+)", re.IGNORECASE),
    re.compile(r"(bearer\s+)([a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
]


def redact_secrets_from_string(text: Any) -> str:
    """Redact known credentials, tokens, and secret parameters from text."""
    if not isinstance(text, str) or not text:
        return ""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1=***REDACTED***", redacted)
    return redacted


def redact_secrets_from_args(args: List[str]) -> List[str]:
    """Redact sensitive arguments safely."""
    redacted_args: List[str] = []
    skip_next = False

    sensitive_flags = {"--password", "--token", "--secret", "--api-key", "--access-key", "-p"}

    for i, arg in enumerate(args):
        if skip_next:
            redacted_args.append("***REDACTED***")
            skip_next = False
            continue

        if arg in sensitive_flags and i + 1 < len(args):
            redacted_args.append(arg)
            skip_next = True
            continue

        # Check for key=value patterns
        redacted_arg = redact_secrets_from_string(arg)
        redacted_args.append(redacted_arg)

    return redacted_args


class CommandRunner:
    """Secure, standardized command execution engine."""

    @staticmethod
    def is_executable_available(executable: str) -> bool:
        """Check if an executable is in PATH or available locally."""
        return shutil.which(executable) is not None

    @staticmethod
    def run_command(
        executable: str,
        args: List[str],
        technology: str,
        capability: str,
        provider_type: str,
        provider_name: str,
        tool_version: Optional[str] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 30.0,
        stdin_content: Optional[str] = None,
        fallback_provider: Optional[str] = None,
    ) -> CommandExecution:
        """Run an external CLI tool securely and record complete execution telemetry."""
        cwd_path = cwd or Path.cwd()
        cmd_list = [executable] + args

        # Build redacted display command
        redacted_args = redact_secrets_from_args(args)
        display_command = " ".join([executable] + redacted_args)

        # Check if executable exists
        if not CommandRunner.is_executable_available(executable):
            return CommandExecution(
                technology=technology,
                capability=capability,
                provider_type=provider_type,
                provider_name=provider_name,
                tool_version=tool_version,
                executable=executable,
                args=redacted_args,
                command=display_command,
                cwd=str(cwd_path),
                exit_code=None,
                status="UNAVAILABLE",
                duration_ms=0.0,
                stdout="",
                stderr="",
                error_message=f"Executable '{executable}' not found in PATH.",
                fallback_provider=fallback_provider,
                unavailable_reason="executable not found",
            )

        start_time = time.perf_counter()
        try:
            # Execute subprocess with strict UTF-8 decoding and replacement for unknown bytes
            res = subprocess.run(
                cmd_list,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                input=stdin_content,
                env=env,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            status = "PASS" if res.returncode == 0 else "FAIL"

            return CommandExecution(
                technology=technology,
                capability=capability,
                provider_type=provider_type,
                provider_name=provider_name,
                tool_version=tool_version,
                executable=executable,
                args=redacted_args,
                command=display_command,
                cwd=str(cwd_path),
                exit_code=res.returncode,
                status=status,
                duration_ms=round(duration_ms, 2),
                stdout=redact_secrets_from_string(res.stdout or ""),
                stderr=redact_secrets_from_string(res.stderr or ""),
                error_message=None if res.returncode == 0 else f"Process exited with code {res.returncode}",
                fallback_provider=fallback_provider,
                unavailable_reason=None,
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CommandExecution(
                technology=technology,
                capability=capability,
                provider_type=provider_type,
                provider_name=provider_name,
                tool_version=tool_version,
                executable=executable,
                args=redacted_args,
                command=display_command,
                cwd=str(cwd_path),
                exit_code=-1,
                status="DEGRADED",
                duration_ms=round(duration_ms, 2),
                stdout="",
                stderr="",
                error_message=f"Execution timed out after {timeout_seconds}s.",
                fallback_provider=fallback_provider,
                unavailable_reason=f"timeout ({timeout_seconds}s)",
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CommandExecution(
                technology=technology,
                capability=capability,
                provider_type=provider_type,
                provider_name=provider_name,
                tool_version=tool_version,
                executable=executable,
                args=redacted_args,
                command=display_command,
                cwd=str(cwd_path),
                exit_code=None,
                status="DEGRADED",
                duration_ms=round(duration_ms, 2),
                stdout="",
                stderr="",
                error_message=str(e),
                fallback_provider=fallback_provider,
                unavailable_reason=f"execution exception: {e}",
            )
