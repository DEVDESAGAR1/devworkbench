"""Dockerfile adapter utilizing Hadolint for container build best-practice linting."""

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


class DockerAdapter(BaseAdapter):
    """Adapter for Dockerfiles utilizing Hadolint."""

    @property
    def technology(self) -> Technology:
        return Technology.DOCKERFILE

    @property
    def name(self) -> str:
        return "Hadolint"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("hadolint"):
            return True, None
        return False, ToolWarning(
            technology=Technology.DOCKERFILE,
            tool_name="Hadolint",
            install_hint="Install Hadolint (https://github.com/hadolint/hadolint) to enable Dockerfile best-practice linting.",
            documentation_url="https://github.com/hadolint/hadolint",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not self.find_tool("hadolint"):
            return diagnostics

        rel_path = detection.relative_path

        try:
            proc = subprocess.run(
                ["hadolint", "-f", "json", str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if proc.stdout.strip():
                try:
                    items = json.loads(proc.stdout)
                    for item in items:
                        level_str = item.get("level", "warning").lower()
                        if level_str == "error":
                            sev = DiagnosticSeverity.ERROR
                        elif level_str == "warning":
                            sev = DiagnosticSeverity.WARNING
                        elif level_str == "info":
                            sev = DiagnosticSeverity.INFO
                        else:
                            sev = DiagnosticSeverity.HINT

                        code = item.get("code")
                        diagnostics.append(
                            Diagnostic(
                                path=rel_path,
                                line=item.get("line"),
                                column=item.get("column"),
                                severity=sev,
                                rule=code,
                                message=item.get("message", "Dockerfile lint issue"),
                                source="hadolint",
                                category=DiagnosticCategory.LINT,
                                provider="hadolint",
                                provider_priority=1,
                                provider_type="native",
                                rule_origin="Native CLI: hadolint",
                                documentation_url=f"https://github.com/hadolint/hadolint/wiki/{code}" if code else "https://github.com/hadolint/hadolint",
                            )
                        )
                except Exception:
                    pass
        except Exception:
            pass

        return diagnostics
