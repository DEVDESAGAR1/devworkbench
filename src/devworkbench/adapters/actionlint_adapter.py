"""GitHub Actions workflow adapter utilizing actionlint."""

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


class ActionlintAdapter(BaseAdapter):
    """Adapter for GitHub Actions workflows utilizing actionlint."""

    @property
    def technology(self) -> Technology:
        return Technology.GITHUB_ACTIONS

    @property
    def name(self) -> str:
        return "actionlint"

    def is_available(self) -> tuple[bool, ToolWarning | None]:
        if self.find_tool("actionlint"):
            return True, None
        return False, ToolWarning(
            technology=Technology.GITHUB_ACTIONS,
            tool_name="actionlint",
            install_hint="Install actionlint (https://github.com/rhysd/actionlint) to enable GitHub Actions workflow linting.",
            documentation_url="https://github.com/rhysd/actionlint",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if not self.find_tool("actionlint"):
            return diagnostics

        rel_path = detection.relative_path

        exec_res = CommandRunner.run_command(
            executable="actionlint",
            args=["-format", "{{json .}}", str(file_path)],
            technology="GitHub Actions",
            capability="github_actions_lint",
            provider_type="native",
            provider_name="actionlint",
            cwd=file_path.parent,
            timeout_seconds=10.0,
        )
        self.record_execution(exec_res)

        if exec_res.stdout.strip():
            try:
                items = json.loads(exec_res.stdout)
                for item in items:
                    diagnostics.append(
                        Diagnostic(
                            path=rel_path,
                            line=item.get("line"),
                            column=item.get("column"),
                            end_line=item.get("end_line"),
                            end_column=item.get("end_column"),
                            severity=DiagnosticSeverity.ERROR if item.get("kind") == "syntax" else DiagnosticSeverity.WARNING,
                            rule=item.get("kind"),
                            message=item.get("message", "Workflow issue"),
                            source="actionlint",
                            category=DiagnosticCategory.LINT,
                            provider="actionlint",
                            provider_priority=1,
                            provider_type="native",
                            rule_origin="Native CLI: actionlint",
                            documentation_url="https://github.com/rhysd/actionlint",
                        )
                    )
            except Exception:
                pass

        return diagnostics
