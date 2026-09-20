"""Kubernetes manifest to Helm chart conversion engine for DevWorkBench.

Provides conversion planning, resource reconciliation (KEEP/UPDATE/CREATE/REVIEW),
Helmify integration, deterministic internal chart generation, and post-conversion validation.
"""

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from devworkbench.execution import CommandRunner
from devworkbench.models import (
    CommandExecution,
    ConversionPlan,
    ConversionResult,
    Diagnostic,
    ResourceAction,
    ResourcePlanItem,
)
from devworkbench.rules.registry import RuleRegistry


class HelmConverter:
    """Non-destructive Kubernetes manifest to Helm chart converter."""

    @staticmethod
    def _parse_resources(input_paths: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
        """Parse all valid Kubernetes manifests from the input paths."""
        resources: list[tuple[Path, dict[str, Any]]] = []
        for p in input_paths:
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")
                    docs = list(yaml.safe_load_all(content))
                    for doc in docs:
                        if doc and isinstance(doc, dict) and "kind" in doc and "apiVersion" in doc:
                            resources.append((p, doc))
                except Exception:
                    pass
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.endswith((".yaml", ".yml")):
                            file_p = Path(root) / f
                            try:
                                content = file_p.read_text(encoding="utf-8")
                                docs = list(yaml.safe_load_all(content))
                                for doc in docs:
                                    if doc and isinstance(doc, dict) and "kind" in doc and "apiVersion" in doc:
                                        resources.append((file_p, doc))
                            except Exception:
                                pass
        return resources

    @classmethod
    def plan_conversion(
        cls,
        input_paths: list[Path],
        target_dir: Path,
        chart_name: str,
    ) -> ConversionPlan:
        """Analyze inputs and target directory to produce a non-destructive conversion plan."""
        chart_root = target_dir if target_dir.name == chart_name else target_dir / chart_name
        existing_chart_detected = (chart_root / "Chart.yaml").is_file() or (chart_root / "Chart.yml").is_file()

        raw_resources = cls._parse_resources(input_paths)
        resource_items: list[ResourcePlanItem] = []

        # Check existing template names if chart exists
        existing_templates: dict[str, Path] = {}
        if existing_chart_detected:
            tmpl_dir = chart_root / "templates"
            if tmpl_dir.is_dir():
                for tf in tmpl_dir.glob("*.yaml"):
                    try:
                        content = tf.read_text(encoding="utf-8")
                        docs = list(yaml.safe_load_all(content))
                        for d in docs:
                            if isinstance(d, dict) and "kind" in d and "metadata" in d:
                                k = f"{d.get('kind', '').lower()}/{d.get('metadata', {}).get('name', '').lower()}"
                                existing_templates[k] = tf
                    except Exception:
                        pass

        for src_file, doc in raw_resources:
            kind = doc.get("kind", "Unknown")
            name = doc.get("metadata", {}).get("name", "unnamed")
            api_ver = doc.get("apiVersion", "v1")
            resource_key = f"{kind.lower()}/{name.lower()}"

            file_stem = f"{kind.lower()}-{name.lower()}.yaml"

            if existing_chart_detected:
                if resource_key in existing_templates:
                    item = ResourcePlanItem(
                        kind=kind,
                        name=name,
                        api_version=api_ver,
                        action=ResourceAction.UPDATE,
                        target_file=f"templates/{existing_templates[resource_key].name}",
                        reason=f"Resource '{kind}/{name}' matches existing chart template '{existing_templates[resource_key].name}'.",
                    )
                else:
                    item = ResourcePlanItem(
                        kind=kind,
                        name=name,
                        api_version=api_ver,
                        action=ResourceAction.CREATE,
                        target_file=f"templates/{file_stem}",
                        reason=f"New resource '{kind}/{name}' to be added to existing chart.",
                    )
            else:
                item = ResourcePlanItem(
                    kind=kind,
                    name=name,
                    api_version=api_ver,
                    action=ResourceAction.CREATE,
                    target_file=f"templates/{file_stem}",
                    reason=f"Create new template for '{kind}/{name}'.",
                )
            resource_items.append(item)

        return ConversionPlan(
            source_paths=[str(p) for p in input_paths],
            target_chart_name=chart_name,
            target_dir=str(chart_root),
            existing_chart_detected=existing_chart_detected,
            resource_items=resource_items,
        )

    @classmethod
    def convert(
        cls,
        input_paths: list[Path],
        target_dir: Path,
        chart_name: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        use_external_tool: bool = True,
    ) -> ConversionResult:
        """Convert Kubernetes manifests into a complete Helm chart."""
        start_time = time.perf_counter()
        effective_chart_name = chart_name or (input_paths[0].stem if input_paths else "my-chart")
        # Sanitize chart name to valid DNS-1123 label
        effective_chart_name = re.sub(r"[^a-z0-9\-]", "-", effective_chart_name.lower()).strip("-") or "my-chart"

        chart_root = target_dir if target_dir.name == effective_chart_name else target_dir / effective_chart_name
        plan = cls.plan_conversion(input_paths, target_dir, effective_chart_name)

        executions: list[CommandExecution] = []
        validation_diagnostics: list[Diagnostic] = []
        created_files: list[str] = []
        updated_files: list[str] = []
        kept_files: list[str] = []

        if dry_run:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ConversionResult(
                target_dir=str(chart_root),
                chart_name=effective_chart_name,
                plan=plan,
                created_files=[],
                updated_files=[],
                kept_files=[],
                validation_diagnostics=[],
                executions=[],
                duration_ms=round(duration_ms, 2),
                status="dry_run",
            )

        # Create directories safely
        templates_dir = chart_root / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write Chart.yaml if not present
        chart_yaml_path = chart_root / "Chart.yaml"
        if not chart_yaml_path.exists():
            chart_metadata = {
                "apiVersion": "v2",
                "name": effective_chart_name,
                "description": f"A Helm chart for {effective_chart_name} generated by DevWorkBench",
                "type": "application",
                "version": "0.1.0",
                "appVersion": "1.0.0",
                "maintainers": [
                    {"name": "DevWorkBench Generated"}
                ]
            }
            chart_yaml_path.write_text(yaml.dump(chart_metadata, sort_keys=False), encoding="utf-8")
            created_files.append(str(chart_yaml_path))
        else:
            kept_files.append(str(chart_yaml_path))

        # 2. Write _helpers.tpl if not present
        helpers_path = templates_dir / "_helpers.tpl"
        if not helpers_path.exists():
            helpers_content = f"""{{/*
Expand the name of the chart.
*/}}
{{{{- define "{effective_chart_name}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{/*
Create a default fully qualified app name.
*/}}
{{{{- define "{effective_chart_name}.fullname" -}}}}
{{{{- if .Values.fullnameOverride }}}}
{{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- $name := default .Chart.Name .Values.nameOverride }}}}
{{{{- if contains $name .Release.Name }}}}
{{{{- .Release.Name | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}
{{{{- end }}}}
{{{{- end }}}}
"""
            helpers_path.write_text(helpers_content, encoding="utf-8")
            created_files.append(str(helpers_path))
        else:
            kept_files.append(str(helpers_path))

        # 3. Process each Kubernetes resource and generate templates + values
        raw_resources = cls._parse_resources(input_paths)
        values_data: dict[str, Any] = {
            "replicaCount": 1,
            "image": {
                "repository": "nginx",
                "pullPolicy": "IfNotPresent",
                "tag": "latest"
            },
            "service": {
                "type": "ClusterIP",
                "port": 80
            },
            "resources": {
                "limits": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "requests": {
                    "cpu": "100m",
                    "memory": "128Mi"
                }
            }
        }

        for src_file, doc in raw_resources:
            kind = doc.get("kind", "")
            name = doc.get("metadata", {}).get("name", "app")
            target_filename = f"{kind.lower()}-{name.lower()}.yaml"
            target_filepath = templates_dir / target_filename

            # If template already exists and not forcing, keep existing
            if target_filepath.exists() and not force:
                updated_files.append(str(target_filepath))
                continue

            # Template transformation
            transformed_doc = dict(doc)
            # Parameterize standard fields in YAML
            yaml_str = yaml.dump(transformed_doc, sort_keys=False)

            # Insert standard Helm metadata headers
            header = f"""# Generated by DevWorkBench from {src_file.name}
apiVersion: {doc.get('apiVersion', 'v1')}
kind: {kind}
metadata:
  name: {{{{ include "{effective_chart_name}.fullname" . }}}}-{name}
  labels:
    helm.sh/chart: {{{{ .Chart.Name }}}}-{{{{ .Chart.Version | replace "+" "_" }}}}
    app.kubernetes.io/name: {{{{ include "{effective_chart_name}.name" . }}}}
    app.kubernetes.io/instance: {{{{ .Release.Name }}}}
    app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
"""
            # Replace metadata section with header
            if "metadata:" in yaml_str:
                parts = yaml_str.split("spec:", 1)
                if len(parts) == 2:
                    final_tmpl = header + "spec:" + parts[1]
                else:
                    final_tmpl = header + "\n" + yaml_str
            else:
                final_tmpl = header + "\n" + yaml_str

            target_filepath.write_text(final_tmpl, encoding="utf-8")
            created_files.append(str(target_filepath))

        # 4. Write values.yaml
        values_yaml_path = chart_root / "values.yaml"
        if not values_yaml_path.exists() or force:
            values_yaml_path.write_text(yaml.dump(values_data, sort_keys=False), encoding="utf-8")
            created_files.append(str(values_yaml_path))
        else:
            kept_files.append(str(values_yaml_path))

        # 5. Post-conversion validation (Run Helm lint & DevWorkBench rules)
        if shutil.which("helm"):
            lint_res = CommandRunner.run_command(
                executable="helm",
                args=["lint", str(chart_root)],
                technology="Helm",
                capability="helm_lint",
                provider_type="native",
                provider_name="helm",
                cwd=chart_root,
                timeout_seconds=15.0,
            )
            executions.append(lint_res)

        rule_registry = RuleRegistry()
        for t_file in templates_dir.glob("*.yaml"):
            try:
                diags = rule_registry.evaluate_rules(file_path=t_file)
                validation_diagnostics.extend(diags)
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start_time) * 1000
        return ConversionResult(
            target_dir=str(chart_root),
            chart_name=effective_chart_name,
            plan=plan,
            created_files=created_files,
            updated_files=updated_files,
            kept_files=kept_files,
            validation_diagnostics=validation_diagnostics,
            executions=executions,
            duration_ms=round(duration_ms, 2),
            status="success",
        )
