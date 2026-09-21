"""Helmify adapter for Kubernetes manifest to Helm chart baseline conversion."""

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from devworkbench.adapters.base import BaseAdapter
from devworkbench.execution import CommandRunner
from devworkbench.migration.models import DiscoveredResource
from devworkbench.models import (
    CommandExecution,
    Diagnostic,
    FileDetection,
    Technology,
    ToolWarning,
)


@dataclass
class HelmifyResult:
    """Result of invoking Helmify on Kubernetes manifests."""

    success: bool
    execution: CommandExecution
    chart_dir: Path | None = None
    templates: dict[str, str] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    chart_yaml: dict[str, Any] = field(default_factory=dict)
    converted_resources: list[str] = field(default_factory=list)
    unsupported_resources: list[str] = field(default_factory=list)
    error_message: str | None = None


class HelmifyAdapter(BaseAdapter):
    """Adapter for the open-source Helmify CLI converter."""

    @property
    def technology(self) -> Technology:
        return Technology.KUBERNETES

    @property
    def name(self) -> str:
        return "helmify"

    def can_handle(self, detection: FileDetection) -> bool:
        return detection.technology in (Technology.KUBERNETES, Technology.HELM)

    def is_available(self) -> tuple[bool, ToolWarning | None]:
        """Check if helmify executable is available in PATH."""
        avail = self.find_tool("helmify") is not None
        if avail:
            return True, None
        return (
            False,
            ToolWarning(
                technology=self.technology,
                tool_name="helmify",
                install_hint="Install Helmify from https://github.com/arttor/helmify (e.g. brew install helmify, or download binary from GitHub releases)",
                documentation_url="https://github.com/arttor/helmify",
            ),
        )

    def get_version(self) -> str | None:
        """Extract helmify version string."""
        if not self.find_tool("helmify"):
            return None
        try:
            exec_res = CommandRunner.run_command(
                executable="helmify",
                args=["--version"],
                technology="Kubernetes",
                capability="kubernetes_to_helm",
                provider_type="opensource",
                provider_name="helmify",
                timeout_seconds=5.0,
            )
            out = (exec_res.stdout or "") + " " + (exec_res.stderr or "")
            match = re.search(r"v?([0-9]+\.[0-9]+\.[0-9]+)", out)
            if match:
                return match.group(1)
            return out.strip() or "available"
        except Exception:
            return None

    def analyze_file(self, file_path: Path, detection: FileDetection) -> list[Diagnostic]:
        """Helmify is primarily a converter/generator, returning no static lint diagnostics on individual files."""
        return []

    def convert_manifests(
        self,
        resources: list[DiscoveredResource],
        chart_name: str,
        timeout_seconds: float = 30.0,
        working_dir: Path | None = None,
    ) -> HelmifyResult:
        """Convert a list of discovered Kubernetes resources into a baseline Helm chart using Helmify."""
        is_avail, warning = self.is_available()
        if not is_avail:
            dummy_exec = CommandExecution(
                technology="Kubernetes",
                capability="kubernetes_to_helm",
                provider_type="opensource",
                provider_name="helmify",
                executable="helmify",
                args=[chart_name],
                command=f"helmify {chart_name}",
                cwd=str(working_dir or Path.cwd()),
                status="UNAVAILABLE",
                exit_code=None,
                stdout="",
                stderr="",
                duration_ms=0.0,
                unavailable_reason="Helmify executable not found in PATH",
                error_message=warning.install_hint if warning else "helmify not found",
            )
            return HelmifyResult(
                success=False,
                execution=dummy_exec,
                error_message="Helmify executable not found in PATH",
                unsupported_resources=[r.identifier for r in resources],
            )

        # Prepare multi-doc Kubernetes YAML stream
        docs_to_dump = [r.raw_doc for r in resources if isinstance(r.raw_doc, dict)]
        if not docs_to_dump:
            dummy_exec = CommandExecution(
                technology="Kubernetes",
                capability="kubernetes_to_helm",
                provider_type="opensource",
                provider_name="helmify",
                executable="helmify",
                args=[chart_name],
                command=f"helmify {chart_name}",
                cwd=str(working_dir or Path.cwd()),
                status="FAIL",
                exit_code=1,
                stdout="",
                stderr="No valid Kubernetes manifest documents to convert.",
                duration_ms=0.0,
                error_message="No valid Kubernetes manifest documents to convert.",
            )
            return HelmifyResult(
                success=False,
                execution=dummy_exec,
                error_message="No valid Kubernetes manifest documents to convert.",
            )

        yaml_stream = yaml.dump_all(docs_to_dump, sort_keys=False)

        # Execute Helmify in an isolated directory
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="devworkbench-helmify-")
        work_path = Path(temp_dir_obj.name)

        try:
            exec_res = CommandRunner.run_command(
                executable="helmify",
                args=[chart_name],
                technology="Kubernetes",
                capability="kubernetes_to_helm",
                provider_type="opensource",
                provider_name="helmify",
                tool_version=self.get_version(),
                cwd=work_path,
                stdin_content=yaml_stream,
                timeout_seconds=timeout_seconds,
            )
            self.record_execution(exec_res)

            generated_chart_path = work_path / chart_name
            if exec_res.status != "PASS" or not generated_chart_path.is_dir():
                return HelmifyResult(
                    success=False,
                    execution=exec_res,
                    chart_dir=None,
                    error_message=exec_res.stderr or f"Helmify failed with exit code {exec_res.exit_code}",
                    unsupported_resources=[r.identifier for r in resources],
                )

            # Read and normalize Helmify's generated artifacts
            templates: dict[str, str] = {}
            tmpl_dir = generated_chart_path / "templates"
            if tmpl_dir.is_dir():
                for f in tmpl_dir.glob("*.yaml"):
                    try:
                        templates[f.name] = f.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass
                for f in tmpl_dir.glob("*.tpl"):
                    try:
                        templates[f.name] = f.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass

            values_data: dict[str, Any] = {}
            val_file = generated_chart_path / "values.yaml"
            if val_file.is_file():
                try:
                    values_data = yaml.safe_load(val_file.read_text(encoding="utf-8")) or {}
                except Exception:
                    pass

            chart_meta: dict[str, Any] = {}
            meta_file = generated_chart_path / "Chart.yaml"
            if meta_file.is_file():
                try:
                    chart_meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
                except Exception:
                    pass

            # Detect which input resources were successfully converted
            converted: list[str] = []
            unsupported: list[str] = []

            for r in resources:
                kind_lower = r.kind.lower()
                # Check if a template corresponds to this resource
                matched = False
                for tmpl_name, tmpl_content in templates.items():
                    if f"kind: {r.kind}" in tmpl_content or kind_lower in tmpl_name.lower():
                        matched = True
                        break
                if matched:
                    converted.append(r.identifier)
                else:
                    unsupported.append(r.identifier)

            return HelmifyResult(
                success=True,
                execution=exec_res,
                chart_dir=generated_chart_path,
                templates=templates,
                values=values_data,
                chart_yaml=chart_meta,
                converted_resources=converted,
                unsupported_resources=unsupported,
            )
        finally:
            # We preserve temp_dir_obj cleanup via Python reference handling
            pass
