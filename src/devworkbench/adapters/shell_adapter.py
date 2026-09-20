"""Shell / Bash adapter utilizing ShellCheck."""

import json
from pathlib import Path

from devworkbench.adapters.base import BaseAdapter
from devworkbench.execution import CommandRunner
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
    ToolWarning,
)


class ShellAdapter(BaseAdapter):
    """Adapter for Shell and Bash scripts using ShellCheck."""

    @property
    def technology(self) -> Technology:
        return Technology.SHELL

    @property
    def name(self) -> str:
        return "ShellCheck"

    def is_available(self) -> tuple[bool, ToolWarning | None]:
        if self.find_tool("shellcheck"):
            return True, None
        return False, ToolWarning(
            technology=Technology.SHELL,
            tool_name="ShellCheck",
            install_hint="Install ShellCheck (https://www.shellcheck.net) to enable shell script static analysis.",
            documentation_url="https://github.com/koalaman/shellcheck",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if not self.find_tool("shellcheck"):
            return diagnostics

        rel_path = detection.relative_path

        exec_res = CommandRunner.run_command(
            executable="shellcheck",
            args=["-f", "json", str(file_path)],
            technology="Shell",
            capability="shell_lint",
            provider_type="native",
            provider_name="shellcheck",
            cwd=file_path.parent,
            timeout_seconds=10.0,
        )
        self.record_execution(exec_res)

        if exec_res.stdout.strip():
            try:
                comments = json.loads(exec_res.stdout)
                for c in comments:
                    level_str = c.get("level", "warning").lower()
                    if level_str == "error":
                        sev = DiagnosticSeverity.ERROR
                    elif level_str == "warning":
                        sev = DiagnosticSeverity.WARNING
                    else:
                        sev = DiagnosticSeverity.INFO

                    rule_code = f"SC{c.get('code')}" if c.get("code") else None
                    diagnostics.append(
                        Diagnostic(
                            path=rel_path,
                            line=c.get("line"),
                            column=c.get("column"),
                            end_line=c.get("endLine"),
                            end_column=c.get("endColumn"),
                            severity=sev,
                            rule=rule_code,
                            message=c.get("message", "Shell issue"),
                            source="shellcheck",
                            category=DiagnosticCategory.LINT,
                            fix_available=bool(c.get("fix")),
                            provider="shellcheck",
                            provider_priority=1,
                            provider_type="native",
                            rule_origin="Native CLI: shellcheck",
                            documentation_url=f"https://www.shellcheck.net/wiki/{rule_code}" if rule_code else "https://www.shellcheck.net",
                        )
                    )
            except Exception:
                pass

        return diagnostics
