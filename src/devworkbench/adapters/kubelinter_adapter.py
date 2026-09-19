"""Kubernetes schema and best-practice adapter utilizing KubeLinter and kubeconform."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

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


class KubeLinterAdapter(BaseAdapter):
    """Adapter for Kubernetes manifests utilizing KubeLinter and kubeconform."""

    @property
    def technology(self) -> Technology:
        return Technology.KUBERNETES

    @property
    def name(self) -> str:
        return "KubeLinter / kubeconform"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("kube-linter") or self.find_tool("kubeconform"):
            return True, None
        return False, ToolWarning(
            technology=Technology.KUBERNETES,
            tool_name="KubeLinter / kubeconform",
            install_hint="Install KubeLinter (https://github.com/stackrox/kube-linter) or kubeconform (https://github.com/yannh/kubeconform) for Kubernetes validation.",
            documentation_url="https://github.com/stackrox/kube-linter",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        rel_path = detection.relative_path

        # 1. Run kubeconform for OpenAPI / JSONSchema validation if available
        if self.find_tool("kubeconform"):
            exec_res = CommandRunner.run_command(
                executable="kubeconform",
                args=["-output", "json", "-summary=false", str(file_path)],
                technology="Kubernetes",
                capability="kubernetes_schema_validation",
                provider_type="opensource",
                provider_name="kubeconform",
                cwd=file_path.parent,
                timeout_seconds=10.0,
            )
            self.record_execution(exec_res)

            if exec_res.stdout.strip():
                try:
                    results = json.loads(exec_res.stdout)
                    for res in results.get("resources", []):
                        status = res.get("status", "")
                        if status in ["Invalid", "error"]:
                            msg = res.get("msg", "Kubernetes schema validation error")
                            diagnostics.append(
                                Diagnostic(
                                    path=rel_path,
                                    severity=DiagnosticSeverity.ERROR,
                                    rule="kubeconform-schema",
                                    message=msg,
                                    source="kubeconform",
                                    category=DiagnosticCategory.SCHEMA,
                                    provider="kubeconform",
                                    provider_priority=2,
                                    provider_type="opensource",
                                    rule_origin="OpenSource: kubeconform",
                                    documentation_url="https://github.com/yannh/kubeconform",
                                )
                            )
                except Exception:
                    pass

        # 2. Run KubeLinter for security and best practices if available
        if self.find_tool("kube-linter"):
            exec_res = CommandRunner.run_command(
                executable="kube-linter",
                args=["lint", "--format", "json", str(file_path)],
                technology="Kubernetes",
                capability="kubernetes_lint",
                provider_type="opensource",
                provider_name="kube-linter",
                cwd=file_path.parent,
                timeout_seconds=10.0,
            )
            self.record_execution(exec_res)

            if exec_res.stdout.strip():
                try:
                    data = json.loads(exec_res.stdout)
                    for report in data.get("Reports", []):
                        check_name = report.get("Check", "kube-lint")
                        msg = report.get("Message", "Kubernetes lint warning")
                        diagnostics.append(
                            Diagnostic(
                                path=rel_path,
                                severity=DiagnosticSeverity.WARNING,
                                rule=check_name,
                                message=msg,
                                source="kube-linter",
                                category=DiagnosticCategory.LINT,
                                provider="kube-linter",
                                provider_priority=2,
                                provider_type="opensource",
                                rule_origin="OpenSource: kube-linter",
                                documentation_url=f"https://docs.kubelinter.io/#/generated/checks?id={check_name.lower().replace('-', '_')}",
                            )
                        )
                except Exception:
                    pass

        return diagnostics
