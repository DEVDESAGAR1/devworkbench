"""Shell / Bash adapter utilizing ShellCheck."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from devworkbench.adapters.base import BaseAdapter
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

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("shellcheck"):
            return True, None
        return False, ToolWarning(
            technology=Technology.SHELL,
            tool_name="ShellCheck",
            install_hint="Install ShellCheck (https://www.shellcheck.net) to enable shell script static analysis.",
            documentation_url="https://github.com/koalaman/shellcheck",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not self.find_tool("shellcheck"):
            return diagnostics

        rel_path = detection.relative_path

        try:
            proc = subprocess.run(
                ["shellcheck", "-f", "json", str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if proc.stdout.strip():
                try:
                    comments = json.loads(proc.stdout)
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
        except Exception:
            pass

        return diagnostics
