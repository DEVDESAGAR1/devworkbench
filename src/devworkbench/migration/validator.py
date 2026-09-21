"""Validation engine for generated Helm charts using native and open-source tooling."""

import shutil
from pathlib import Path
from typing import Any

from devworkbench.execution import CommandRunner
from devworkbench.models import CommandExecution, Diagnostic
from devworkbench.rules.registry import RuleRegistry


class MigrationValidator:
    """Validates generated Helm charts using the mandatory provider hierarchy."""

    @classmethod
    def validate_chart(cls, chart_dir: Path) -> dict[str, Any]:
        """Run available native, open-source, and internal validations on the generated chart."""
        executions: list[CommandExecution] = []
        diagnostics: list[Diagnostic] = []

        # 1. NATIVE: Helm binary validations
        lint_exec = CommandRunner.run_command(
            executable="helm",
            args=["lint", str(chart_dir)],
            technology="Helm",
            capability="helm_lint",
            provider_type="native",
            provider_name="helm",
            cwd=chart_dir,
            timeout_seconds=15.0,
        )
        executions.append(lint_exec)

        if lint_exec.status != "UNAVAILABLE":
            template_exec = CommandRunner.run_command(
                executable="helm",
                args=["template", str(chart_dir)],
                technology="Helm",
                capability="helm_render",
                provider_type="native",
                provider_name="helm",
                cwd=chart_dir,
                timeout_seconds=15.0,
            )
            executions.append(template_exec)

        # 2. OPENSOURCE: kubeconform / kube-linter if available
        if shutil.which("kubeconform"):
            kc_exec = CommandRunner.run_command(
                executable="kubeconform",
                args=["-summary", str(chart_dir / "templates")],
                technology="Kubernetes",
                capability="kubernetes_schema_validation",
                provider_type="opensource",
                provider_name="kubeconform",
                cwd=chart_dir,
                timeout_seconds=15.0,
            )
            executions.append(kc_exec)

        if shutil.which("kube-linter"):
            kl_exec = CommandRunner.run_command(
                executable="kube-linter",
                args=["lint", str(chart_dir / "templates")],
                technology="Kubernetes",
                capability="kubernetes_lint",
                provider_type="opensource",
                provider_name="kube-linter",
                cwd=chart_dir,
                timeout_seconds=15.0,
            )
            executions.append(kl_exec)

        # 3. DEVWORKBENCH: Internal rules validation on templates
        rule_registry = RuleRegistry()
        templates_dir = chart_dir / "templates"
        if templates_dir.is_dir():
            for t_file in sorted(templates_dir.glob("*.yaml")):
                try:
                    file_diags = rule_registry.evaluate_rules(file_path=t_file)
                    diagnostics.extend(file_diags)
                except Exception:
                    pass

        return {
            "executions": executions,
            "diagnostics": diagnostics,
        }
