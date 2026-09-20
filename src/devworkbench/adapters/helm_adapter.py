"""Helm adapter utilizing the Helm CLI for chart linting and template rendering."""

import re
import shutil
import tempfile
from pathlib import Path

from devworkbench.adapters.base import BaseAdapter
from devworkbench.execution import CommandRunner
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
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

    def is_available(self) -> tuple[bool, ToolWarning | None]:
        if self.find_tool("helm"):
            return True, None
        return False, ToolWarning(
            technology=Technology.HELM,
            tool_name="Helm",
            install_hint="Install Helm (https://helm.sh/docs/intro/install/) to enable chart linting and template validation.",
            documentation_url="https://helm.sh",
        )

    def analyze_project(
        self, project_path: Path, chart: HelmChart | None = None
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if not self.find_tool("helm") or not chart:
            return diagnostics

        chart_dir = Path(chart.root_path)
        rel_root = chart.relative_root

        # 1. Run 'helm lint'
        lint_res = CommandRunner.run_command(
            executable="helm",
            args=["lint", str(chart_dir)],
            technology="Helm",
            capability="helm_lint",
            provider_type="native",
            provider_name="helm",
            cwd=chart_dir,
            timeout_seconds=15.0,
        )
        self.record_execution(lint_res)

        if lint_res.exit_code != 0 or "[ERROR]" in lint_res.stdout or "[WARNING]" in lint_res.stdout:
            output = lint_res.stdout + "\n" + lint_res.stderr
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

        # 2. Run 'helm template' into temporary directory for dry-run validation
        with tempfile.TemporaryDirectory(prefix="devworkbench_helm_") as temp_dir:
            tmpl_res = CommandRunner.run_command(
                executable="helm",
                args=["template", chart.name, str(chart_dir), "--output-dir", temp_dir],
                technology="Helm",
                capability="helm_render",
                provider_type="native",
                provider_name="helm",
                cwd=chart_dir,
                timeout_seconds=15.0,
            )
            self.record_execution(tmpl_res)

            if tmpl_res.exit_code != 0:
                err_msg = tmpl_res.stderr.strip() or "Template rendering failed"
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
                # If rendering succeeded, run kubeconform on the rendered output if available
                if shutil.which("kubeconform"):
                    kc_res = CommandRunner.run_command(
                        executable="kubeconform",
                        args=["-summary=false", "-output", "json", temp_dir],
                        technology="Kubernetes",
                        capability="kubernetes_schema_validation",
                        provider_type="opensource",
                        provider_name="kubeconform",
                        cwd=chart_dir,
                        timeout_seconds=15.0,
                    )
                    self.record_execution(kc_res)

        return diagnostics
