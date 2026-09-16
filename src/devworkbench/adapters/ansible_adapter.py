"""Ansible adapter utilizing ansible-lint."""

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


class AnsibleLintAdapter(BaseAdapter):
    """Adapter for Ansible playbooks and tasks utilizing ansible-lint."""

    @property
    def technology(self) -> Technology:
        return Technology.ANSIBLE

    @property
    def name(self) -> str:
        return "ansible-lint"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("ansible-lint"):
            return True, None
        return False, ToolWarning(
            technology=Technology.ANSIBLE,
            tool_name="ansible-lint",
            install_hint="Install ansible-lint via 'pip install ansible-lint' to enable Ansible playbook linting.",
            documentation_url="https://ansible.readthedocs.io/projects/lint/",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not self.find_tool("ansible-lint"):
            return diagnostics

        rel_path = detection.relative_path

        try:
            proc = subprocess.run(
                ["ansible-lint", "--format", "json", str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if proc.stdout.strip():
                try:
                    items = json.loads(proc.stdout)
                    for item in items:
                        rule = item.get("check_name") or item.get("rule", {}).get("id")
                        diagnostics.append(
                            Diagnostic(
                                path=rel_path,
                                line=item.get("location", {}).get("lines", {}).get("begin"),
                                severity=DiagnosticSeverity.WARNING,
                                rule=rule,
                                message=item.get("description", "Ansible lint warning"),
                                source="ansible-lint",
                                category=DiagnosticCategory.LINT,
                                provider="ansible-lint",
                                provider_priority=2,
                                provider_type="opensource",
                                rule_origin="OpenSource: ansible-lint",
                                documentation_url="https://ansible.readthedocs.io/projects/lint/",
                            )
                        )
                except Exception:
                    pass
        except Exception:
            pass

        return diagnostics
