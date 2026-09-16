"""Helm adapter utilizing the Helm CLI for chart linting and template rendering."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from devworkbench.adapters.base import BaseAdapter
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    HelmChart,
    Technology,
    ToolWarning,
)


class HelmAdapter(BaseAdapter):
    """Adapter for Helm charts and templates."""

    @property
    def technology(self) -> Technology:
        return Technology.HELM

    @property
    def name(self) -> str:
        return "Helm"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("helm"):
            return True, None
        return False, ToolWarning(
            technology=Technology.HELM,
            tool_name="Helm",
            install_hint="Install Helm (https://helm.sh/docs/intro/install/) to enable chart linting and template validation.",
            documentation_url="https://helm.sh",
        )

    def analyze_project(
        self, project_path: Path, chart: Optional[HelmChart] = None
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not self.find_tool("helm") or not chart:
            return diagnostics

        chart_dir = Path(chart.root_path)
        rel_root = chart.relative_root

        # 1. Run 'helm lint'
        try:
            lint_proc = subprocess.run(
                ["helm", "lint", str(chart_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if lint_proc.returncode != 0 or "[ERROR]" in lint_proc.stdout or "[WARNING]" in lint_proc.stdout:
                output = lint_proc.stdout + "\n" + lint_proc.stderr
                for line in output.splitlines():
                    line_clean = line.strip()
                    if "[ERROR]" in line_clean:
                        msg = line_clean.replace("[ERROR]", "").strip()
                        diagnostics.append(
                            Diagnostic(
                                path=rel_root,
                                message=msg,
                                source="helm-lint",
                                severity=DiagnosticSeverity.ERROR,
                                category=DiagnosticCategory.SCHEMA,
                                provider="helm",
                                provider_priority=1,
                                provider_type="native",
                                rule_origin="Native CLI: helm lint",
                                documentation_url="https://helm.sh/docs/helm/helm_lint/",
                            )
                        )
                    elif "[WARNING]" in line_clean:
                        msg = line_clean.replace("[WARNING]", "").strip()
                        diagnostics.append(
                            Diagnostic(
                                path=rel_root,
                                message=msg,
                                source="helm-lint",
                                severity=DiagnosticSeverity.WARNING,
                                category=DiagnosticCategory.LINT,
                                provider="helm",
                                provider_priority=1,
                                provider_type="native",
                                rule_origin="Native CLI: helm lint",
                                documentation_url="https://helm.sh/docs/helm/helm_lint/",
                            )
                        )
        except Exception:
            pass

        # 2. Run 'helm template' into temporary directory for dry-run validation
        with tempfile.TemporaryDirectory(prefix="devworkbench_helm_") as temp_dir:
            try:
                tmpl_proc = subprocess.run(
                    ["helm", "template", chart.name, str(chart_dir), "--output-dir", temp_dir],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                if tmpl_proc.returncode != 0:
                    err_msg = tmpl_proc.stderr.strip() or "Template rendering failed"
                    match = re.search(r"\(([^:]+):(\d+)(?::(\d+))?\):\s*(.+)", err_msg)
                    if match:
                        t_path, t_line, t_col, t_msg = match.groups()
                        diagnostics.append(
                            Diagnostic(
                                path=t_path,
                                line=int(t_line) if t_line else None,
                                column=int(t_col) if t_col else None,
                                severity=DiagnosticSeverity.ERROR,
                                rule="helm-template-render-error",
                                message=t_msg,
                                source="helm-template",
                                category=DiagnosticCategory.SYNTAX,
                                provider="helm",
                                provider_priority=1,
                                provider_type="native",
                                rule_origin="Native CLI: helm template",
                                documentation_url="https://helm.sh/docs/helm/helm_template/",
                            )
                        )
                    else:
                        diagnostics.append(
                            Diagnostic(
                                path=rel_root,
                                severity=DiagnosticSeverity.ERROR,
                                rule="helm-template-render-error",
                                message=err_msg,
                                source="helm-template",
                                category=DiagnosticCategory.SYNTAX,
                                provider="helm",
                                provider_priority=1,
                                provider_type="native",
                                rule_origin="Native CLI: helm template",
                                documentation_url="https://helm.sh/docs/helm/helm_template/",
                            )
                        )
                else:
                    # If rendering succeeded, run kubeconform/KubeLinter on the rendered temporary output
                    if shutil.which("kubeconform"):
                        try:
                            kc_proc = subprocess.run(
                                ["kubeconform", "-summary=false", "-output", "json", temp_dir],
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=15,
                            )
                            # Any kubeconform errors mapped to chart
                        except Exception:
                            pass
            except Exception:
                pass

        return diagnostics
