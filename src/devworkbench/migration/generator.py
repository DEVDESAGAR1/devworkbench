"""Reference-aware Helm chart generator for DevWorkBench."""

import re
import time
from pathlib import Path
from typing import Any

import yaml

from devworkbench.migration.models import (
    DiscoveredResource,
    MigrationPlan,
    MigrationPlanItem,
    MigrationResult,
    ReferencePattern,
)


class HelmGenerator:
    """Generates an idiomatic Helm chart from discovered Kubernetes manifests and optional reference conventions."""

    @classmethod
    def plan(
        cls,
        resources: list[DiscoveredResource],
        target_dir: Path,
        chart_name: str,
        reference: ReferencePattern | None = None,
        provider_preference: str = "auto",
    ) -> MigrationPlan:
        """Create a non-destructive migration plan mapping input resources to Helm templates."""
        effective_chart_name = cls._sanitize_name(chart_name)
        chart_root = target_dir

        from devworkbench.capabilities.model import CapabilityType
        from devworkbench.capabilities.resolver import CapabilityResolver

        resolver = CapabilityResolver()
        cap_res = resolver.resolve(CapabilityType.KUBERNETES_TO_HELM, preference=provider_preference)
        is_helmify = (
            cap_res.selected_provider is not None
            and cap_res.selected_provider.name == "helmify"
            and cap_res.selected_provider.is_available
        )

        items: list[MigrationPlanItem] = []

        for r in resources:
            kind_lower = r.kind.lower()
            target_filename = cls._determine_template_filename(r)
            pattern_name = reference.name if reference else None

            if is_helmify:
                provider = "Helmify"
                priority = "OPEN_SOURCE"
                if reference:
                    reason = f"Delegated to Open Source Helmify converter; conventions applied from '{reference.name}'."
                else:
                    reason = f"Delegated to Open Source Helmify converter for {r.kind}/{r.name}."
            else:
                # Fallback or standard DevWorkBench logic
                priority = "DEVWORKBENCH"
                if reference and any(kind_lower in tf.lower() for tf in reference.templates_found):
                    provider = "reference-pattern"
                    reason = f"Synthesized from {r.kind}/{r.name} using conventions from '{reference.name}'."
                else:
                    provider = "DEVWORKBENCH"
                    reason = f"Synthesized from {r.kind}/{r.name} using DevWorkBench standard patterns."

            items.append(
                MigrationPlanItem(
                    source_resource=f"{r.kind}/{r.name}",
                    kind=r.kind,
                    target_file=f"templates/{target_filename}",
                    pattern_applied=pattern_name,
                    provider=provider,
                    priority=priority,
                    reason=reason,
                )
            )

        from devworkbench.migration.relationships import RelationshipAnalyzer

        relationships = RelationshipAnalyzer.analyze(resources)

        return MigrationPlan(
            input_directory=str(Path(resources[0].source_file).parent) if resources else ".",
            target_chart_name=effective_chart_name,
            target_directory=str(chart_root),
            reference_name=reference.name if reference else None,
            discovered_resources=resources,
            relationships=relationships,
            planned_items=items,
        )

    @staticmethod
    def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge override dictionary into base dictionary."""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                HelmGenerator._deep_merge_dict(base[k], v)
            else:
                base[k] = v
        return base

    @classmethod
    def generate(
        cls,
        resources: list[DiscoveredResource],
        target_dir: Path,
        chart_name: str | None = None,
        reference: ReferencePattern | None = None,
        provider_preference: str = "auto",
        dry_run: bool = False,
        force: bool = False,
    ) -> MigrationResult:
        """Generate the complete Helm chart directory structure, templates, and values."""
        start_time = time.perf_counter()

        if not resources:
            raise ValueError("Cannot generate Helm chart: no Kubernetes resources discovered in input.")

        # Determine chart name
        default_name = resources[0].name or "my-chart"
        raw_name = chart_name or default_name
        effective_name = cls._sanitize_name(raw_name)

        chart_root = target_dir
        templates_dir = chart_root / "templates"

        plan = cls.plan(
            resources,
            target_dir,
            effective_name,
            reference=reference,
            provider_preference=provider_preference,
        )

        if dry_run:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                target_dir=str(chart_root),
                chart_name=effective_name,
                plan=plan,
                created_files=[],
                updated_files=[],
                kept_files=[],
                validation_executions=[],
                validation_diagnostics=[],
                duration_ms=round(duration_ms, 2),
                status="dry_run",
            )

        # Create directories safely
        templates_dir.mkdir(parents=True, exist_ok=True)

        created_files: list[str] = []
        updated_files: list[str] = []
        kept_files: list[str] = []
        validation_executions: list[Any] = []

        helper_prefix = (reference.helper_prefix if reference else None) or effective_name
        has_hpa = any(r.kind.lower() == "horizontalpodautoscaler" for r in resources)

        # Query CapabilityResolver
        from devworkbench.adapters.helmify_adapter import HelmifyAdapter
        from devworkbench.capabilities.model import CapabilityType
        from devworkbench.capabilities.resolver import CapabilityResolver

        resolver = CapabilityResolver()
        cap_res = resolver.resolve(CapabilityType.KUBERNETES_TO_HELM, preference=provider_preference)
        use_helmify = (
            cap_res.selected_provider is not None
            and cap_res.selected_provider.name == "helmify"
            and cap_res.selected_provider.is_available
        )

        helmify_succeeded = False
        helmify_result = None

        if use_helmify:
            adapter = HelmifyAdapter()
            helmify_result = adapter.convert_manifests(
                resources=resources,
                chart_name=effective_name,
                working_dir=target_dir.parent if target_dir.parent.exists() else None,
            )
            if helmify_result.execution:
                validation_executions.append(helmify_result.execution)

            if helmify_result.success:
                helmify_succeeded = True
            else:
                for item in plan.planned_items:
                    item.provider = "DevWorkBench"
                    item.priority = "DEVWORKBENCH"
                    item.reason = f"Synthesized by DevWorkBench internal generator (fallback: Helmify failed: {helmify_result.error_message})."

        if helmify_succeeded and helmify_result:
            # 1. Chart.yaml
            chart_yaml_path = chart_root / "Chart.yaml"
            if not chart_yaml_path.exists() or force:
                chart_meta = {
                    "apiVersion": "v2",
                    "name": effective_name,
                    "description": f"A Helm chart for {effective_name} generated by DevWorkBench",
                    "type": "application",
                    "version": "0.1.0",
                    "appVersion": "1.0.0",
                }
                if helmify_result.chart_yaml:
                    chart_meta.update({k: v for k, v in helmify_result.chart_yaml.items() if k in ("apiVersion", "name", "version", "appVersion", "description")})
                chart_yaml_path.write_text(yaml.dump(chart_meta, sort_keys=False), encoding="utf-8")
                created_files.append(str(chart_yaml_path))
            else:
                kept_files.append(str(chart_yaml_path))

            # 2. _helpers.tpl
            helpers_path = templates_dir / "_helpers.tpl"
            if not helpers_path.exists() or force:
                helpers_content = cls._generate_helpers(helper_prefix, effective_name)
                helpers_path.write_text(helpers_content, encoding="utf-8")
                created_files.append(str(helpers_path))
            else:
                kept_files.append(str(helpers_path))

            # 3. .helmignore
            helmignore_path = chart_root / ".helmignore"
            if not helmignore_path.exists() or force:
                ignore_content = cls._generate_helmignore()
                helmignore_path.write_text(ignore_content, encoding="utf-8")
                created_files.append(str(helmignore_path))
            else:
                kept_files.append(str(helmignore_path))

            # 4. NOTES.txt
            notes_path = templates_dir / "NOTES.txt"
            if not notes_path.exists() or force:
                notes_content = cls._generate_notes(helper_prefix)
                notes_path.write_text(notes_content, encoding="utf-8")
                created_files.append(str(notes_path))
            else:
                kept_files.append(str(notes_path))

            # 5. Templates for Discovered Resources ONLY (Strict Resource Existence Rule)
            for r in resources:
                target_filename = cls._determine_template_filename(r)
                target_filepath = templates_dir / target_filename

                if target_filepath.exists() and not force:
                    kept_files.append(str(target_filepath))
                    continue

                # Match template from Helmify result
                matching_content = None
                for t_name, t_content in helmify_result.templates.items():
                    if t_name == target_filename:
                        matching_content = t_content
                        break
                    if r.kind.lower() in t_name.lower() or f"kind: {r.kind}" in t_content:
                        matching_content = t_content
                        break

                # HPA is preserved faithfully with autoscaling/v2
                if r.kind.lower() == "horizontalpodautoscaler":
                    template_content = cls._generate_resource_template(
                        resource=r,
                        helper_prefix=helper_prefix,
                        chart_name=effective_name,
                        has_hpa=has_hpa,
                        reference=reference,
                    )
                    for item in plan.planned_items:
                        if item.source_resource == f"{r.kind}/{r.name}":
                            item.provider = "DevWorkBench"
                            item.priority = "DEVWORKBENCH"
                            item.reason = "Faithfully preserved by DevWorkBench (autoscaling/v2 rules)."
                            break
                elif matching_content:
                    template_content = matching_content
                    # Ensure HPA gating in deployment if has_hpa
                    if r.kind.lower() == "deployment" and has_hpa:
                        if "if not .Values.autoscaling.enabled" not in template_content:
                            template_content = re.sub(
                                r"(replicas:\s*\{\{[^\}]+\}\}|\b(replicas:\s*\d+))",
                                """{{- if not .Values.autoscaling.enabled }}\n  replicas: {{ .Values.replicaCount }}\n  {{- end }}""",
                                template_content,
                                count=1,
                            )
                    for item in plan.planned_items:
                        if item.source_resource == f"{r.kind}/{r.name}":
                            item.provider = "Helmify"
                            item.priority = "OPEN_SOURCE"
                            item.reason = f"Converted via Open Source Helmify converter for {r.kind}/{r.name}."
                            break
                else:
                    template_content = cls._generate_resource_template(
                        resource=r,
                        helper_prefix=helper_prefix,
                        chart_name=effective_name,
                        has_hpa=has_hpa,
                        reference=reference,
                    )
                    for item in plan.planned_items:
                        if item.source_resource == f"{r.kind}/{r.name}":
                            item.provider = "DevWorkBench"
                            item.priority = "DEVWORKBENCH"
                            item.reason = f"Synthesized by DevWorkBench (Helmify omitted {r.kind})."
                            break

                target_filepath.write_text(template_content, encoding="utf-8")
                created_files.append(str(target_filepath))

            # 6. values.yaml
            values_path = chart_root / "values.yaml"
            if not values_path.exists() or force:
                values_data = cls._init_values_structure(resources, reference)
                if helmify_result.values:
                    cls._deep_merge_dict(values_data, helmify_result.values)
                values_path.write_text(yaml.dump(values_data, sort_keys=False), encoding="utf-8")
                created_files.append(str(values_path))
            else:
                kept_files.append(str(values_path))

        else:
            # Standard DevWorkBench generation
            # 1. Chart.yaml
            chart_yaml_path = chart_root / "Chart.yaml"
            if not chart_yaml_path.exists() or force:
                chart_meta = {
                    "apiVersion": "v2",
                    "name": effective_name,
                    "description": f"A Helm chart for {effective_name} generated by DevWorkBench",
                    "type": "application",
                    "version": "0.1.0",
                    "appVersion": "1.0.0",
                }
                chart_yaml_path.write_text(yaml.dump(chart_meta, sort_keys=False), encoding="utf-8")
                created_files.append(str(chart_yaml_path))
            else:
                kept_files.append(str(chart_yaml_path))

            # 2. _helpers.tpl
            helpers_path = templates_dir / "_helpers.tpl"
            if not helpers_path.exists() or force:
                helpers_content = cls._generate_helpers(helper_prefix, effective_name)
                helpers_path.write_text(helpers_content, encoding="utf-8")
                created_files.append(str(helpers_path))
            else:
                kept_files.append(str(helpers_path))

            # 3. .helmignore
            helmignore_path = chart_root / ".helmignore"
            if not helmignore_path.exists() or force:
                ignore_content = cls._generate_helmignore()
                helmignore_path.write_text(ignore_content, encoding="utf-8")
                created_files.append(str(helmignore_path))
            else:
                kept_files.append(str(helmignore_path))

            # 4. NOTES.txt
            notes_path = templates_dir / "NOTES.txt"
            if not notes_path.exists() or force:
                notes_content = cls._generate_notes(helper_prefix)
                notes_path.write_text(notes_content, encoding="utf-8")
                created_files.append(str(notes_path))
            else:
                kept_files.append(str(notes_path))

            # 5. Resource Templates (ONLY for resources in input!)
            values_data = cls._init_values_structure(resources, reference)

            for r in resources:
                target_filename = cls._determine_template_filename(r)
                target_filepath = templates_dir / target_filename

                if target_filepath.exists() and not force:
                    kept_files.append(str(target_filepath))
                    continue

                template_content = cls._generate_resource_template(
                    resource=r,
                    helper_prefix=helper_prefix,
                    chart_name=effective_name,
                    has_hpa=has_hpa,
                    reference=reference,
                )
                target_filepath.write_text(template_content, encoding="utf-8")
                created_files.append(str(target_filepath))

            # 6. values.yaml
            values_path = chart_root / "values.yaml"
            if not values_path.exists() or force:
                values_path.write_text(yaml.dump(values_data, sort_keys=False), encoding="utf-8")
                created_files.append(str(values_path))
            else:
                kept_files.append(str(values_path))

        # 7. Native and Open-Source Validations
        from devworkbench.migration.validator import MigrationValidator

        validation_res = MigrationValidator.validate_chart(chart_root)
        all_executions = validation_executions + validation_res.get("executions", [])

        duration_ms = (time.perf_counter() - start_time) * 1000
        return MigrationResult(
            target_dir=str(chart_root),
            chart_name=effective_name,
            plan=plan,
            created_files=created_files,
            updated_files=updated_files,
            kept_files=kept_files,
            validation_executions=all_executions,
            validation_diagnostics=validation_res.get("diagnostics", []),
            duration_ms=round(duration_ms, 2),
            status="success",
        )

    @staticmethod
    def _sanitize_name(name: str) -> str:
        clean = re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")
        return clean or "my-chart"

    @staticmethod
    def _determine_template_filename(resource: DiscoveredResource) -> str:
        kind_lower = resource.kind.lower()
        if kind_lower == "horizontalpodautoscaler":
            return "hpa.yaml"
        if kind_lower == "deployment":
            return "deployment.yaml"
        if kind_lower == "service":
            return "service.yaml"
        if kind_lower == "ingress":
            return "ingress.yaml"
        if kind_lower == "serviceaccount":
            return "serviceaccount.yaml"
        # For multiple instances of other resources, include name
        clean_name = re.sub(r"[^a-z0-9\-]", "-", resource.name.lower()).strip("-")
        return f"{kind_lower}-{clean_name}.yaml"

    @classmethod
    def _generate_helpers(cls, prefix: str, chart_name: str) -> str:
        helpers = f"""{{/*
Expand the name of the chart.
*/}}
{{{{- define "{prefix}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{/*
Create a default fully qualified app name.
*/}}
{{{{- define "{prefix}.fullname" -}}}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{{{- define "{prefix}.chart" -}}}}
{{{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{/*
Common labels
*/}}
{{{{- define "{prefix}.labels" -}}}}
helm.sh/chart: {{{{ include "{prefix}.chart" . }}}}
{{{{ include "{prefix}.selectorLabels" . }}}}
{{{{- if .Chart.AppVersion }}}}
app.kubernetes.io/version: {{{{ .Chart.AppVersion | quote }}}}
{{{{- end }}}}
app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
{{{{- end }}}}

{{/*
Selector labels
*/}}
{{{{- define "{prefix}.selectorLabels" -}}}}
app.kubernetes.io/name: {{{{ include "{prefix}.name" . }}}}
app.kubernetes.io/instance: {{{{ .Release.Name }}}}
{{{{- end }}}}

{{/*
Create the name of the service account to use
*/}}
{{{{- define "{prefix}.serviceAccountName" -}}}}
{{{{- if .Values.serviceAccount.create }}}}
{{{{- default (include "{prefix}.fullname" .) .Values.serviceAccount.name }}}}
{{{{- else }}}}
{{{{- default "default" .Values.serviceAccount.name }}}}
{{{{- end }}}}
{{{{- end }}}}
"""
        if prefix != chart_name:
            helpers += f"""
{{/* Aliases mapping {chart_name} to {prefix} helpers */}}
{{{{- define "{chart_name}.name" -}}}}
{{{{- include "{prefix}.name" . }}}}
{{{{- end }}}}

{{{{- define "{chart_name}.fullname" -}}}}
{{{{- include "{prefix}.fullname" . }}}}
{{{{- end }}}}

{{{{- define "{chart_name}.chart" -}}}}
{{{{- include "{prefix}.chart" . }}}}
{{{{- end }}}}

{{{{- define "{chart_name}.labels" -}}}}
{{{{- include "{prefix}.labels" . }}}}
{{{{- end }}}}

{{{{- define "{chart_name}.selectorLabels" -}}}}
{{{{- include "{prefix}.selectorLabels" . }}}}
{{{{- end }}}}

{{{{- define "{chart_name}.serviceAccountName" -}}}}
{{{{- include "{prefix}.serviceAccountName" . }}}}
{{{{- end }}}}
"""
        return helpers

    @staticmethod
    def _generate_helmignore() -> str:
        return """# Patterns to ignore when packaging Helm charts.
.DS_Store
.git/
.gitignore
.bzr/
.hg/
*.swp
*.bak
*.tmp
*.orig
*~
.project
.idea/
*.tmproj
.vscode/
"""

    @classmethod
    def _generate_notes(cls, prefix: str) -> str:
        return f"""1. Get the application URL by running these commands:
{{{{- if .Values.ingress.enabled }}}}
{{{{- range $host := .Values.ingress.hosts }}}}
  http{{{{ if $.Values.ingress.tls }}}}s{{{{ end }}}}://{{{{ $host.host }}}}{{{{ range .paths }}}}{{{{ .path }}}}{{{{ end }}}}
{{{{- end }}}}
{{{{- else if contains "NodePort" .Values.service.type }}}}
  export NODE_PORT=$(kubectl get --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{{{.spec.ports[0].nodePort}}}}" services {{{{ include "{prefix}.fullname" . }}}})
  export NODE_IP=$(kubectl get nodes --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{{{.items[0].status.addresses[0].address}}}}")
  echo http://$NODE_IP:$NODE_PORT
{{{{- else if contains "LoadBalancer" .Values.service.type }}}}
     NOTE: It may take a few minutes for the LoadBalancer IP to be available.
           You can watch the status by running:
           kubectl get svc --namespace {{{{ .Release.Namespace }}}} -w {{{{ include "{prefix}.fullname" . }}}}
{{{{- else if contains "ClusterIP" .Values.service.type }}}}
  export POD_NAME=$(kubectl get pods --namespace {{{{ .Release.Namespace }}}} -l "{{{{ include "{prefix}.selectorLabels" . }}}}" -o jsonpath="{{{{.items[0].metadata.name}}}}")
  echo "Visit http://127.0.0.1:8080 to use your application"
  kubectl --namespace {{{{ .Release.Namespace }}}} port-forward $POD_NAME 8080:{{{{ .Values.service.port }}}}
{{{{- end }}}}
"""

    @classmethod
    def _init_values_structure(
        cls,
        resources: list[DiscoveredResource],
        reference: ReferencePattern | None = None,
    ) -> dict[str, Any]:
        """Synthesize values.yaml structure based on discovered resources and reference conventions."""
        has_hpa = False
        hpa_res: DiscoveredResource | None = None
        has_ingress = False
        svc_port = 80
        svc_type = "ClusterIP"
        image_repo = "app"
        image_tag = "latest"
        image_pull_policy = "IfNotPresent"
        replicas = 1

        for r in resources:
            k = r.kind.lower()
            if k == "horizontalpodautoscaler":
                has_hpa = True
                hpa_res = r
            elif k == "ingress":
                has_ingress = True
            elif k == "service":
                svc_type = r.spec.get("type", "ClusterIP")
                ports = r.spec.get("ports", [])
                if ports and isinstance(ports[0], dict):
                    svc_port = ports[0].get("port", 80)
            elif k in ("deployment", "statefulset"):
                if "replicas" in r.spec:
                    try:
                        replicas = int(r.spec["replicas"])
                    except Exception:
                        pass
                pod_spec = r.spec.get("template", {}).get("spec", {})
                containers = pod_spec.get("containers", [])
                if containers and isinstance(containers[0], dict):
                    c0 = containers[0]
                    img = str(c0.get("image", "app:latest"))
                    if ":" in img:
                        image_repo, image_tag = img.split(":", 1)
                    else:
                        image_repo = img
                    image_pull_policy = c0.get("imagePullPolicy", "IfNotPresent")

        values: dict[str, Any] = {
            "replicaCount": replicas,
            "image": {
                "repository": image_repo,
                "pullPolicy": image_pull_policy,
                "tag": image_tag,
            },
            "imagePullSecrets": [],
            "nameOverride": "",
            "fullnameOverride": "",
            "serviceAccount": {
                "create": True,
                "annotations": {},
                "name": "",
            },
            "service": {
                "type": svc_type,
                "port": svc_port,
            },
            "resources": {
                "limits": {
                    "cpu": "500m",
                    "memory": "512Mi",
                },
                "requests": {
                    "cpu": "100m",
                    "memory": "128Mi",
                },
            },
        }

        # First-class HPA support
        if has_hpa and hpa_res:
            spec = hpa_res.spec
            min_r = spec.get("minReplicas", 1)
            max_r = spec.get("maxReplicas", 10)
            target_cpu = 80
            metrics = spec.get("metrics", [])
            for m in metrics:
                if isinstance(m, dict) and m.get("type") == "Resource":
                    res_m = m.get("resource", {})
                    if res_m.get("name") == "cpu":
                        target_cpu = res_m.get("target", {}).get("averageUtilization", 80)

            values["autoscaling"] = {
                "enabled": True,
                "minReplicas": min_r,
                "maxReplicas": max_r,
                "targetCPUUtilizationPercentage": target_cpu,
            }

        # Ingress support
        if has_ingress:
            values["ingress"] = {
                "enabled": True,
                "className": "",
                "annotations": {},
                "hosts": [
                    {
                        "host": "chart-example.local",
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "ImplementationSpecific",
                            }
                        ],
                    }
                ],
                "tls": [],
            }

        # Reference values hierarchy merge
        if reference and reference.values_hierarchy:
            cls._deep_merge_dict(values, reference.values_hierarchy)

        return values

    @classmethod
    def _generate_resource_template(
        cls,
        resource: DiscoveredResource,
        helper_prefix: str,
        chart_name: str,
        has_hpa: bool = False,
        reference: ReferencePattern | None = None,
    ) -> str:
        """Synthesize idiomatic Go template for a specific resource."""
        k = resource.kind.lower()

        if k == "deployment":
            return cls._generate_deployment_template(resource, helper_prefix, has_hpa)
        if k == "service":
            return cls._generate_service_template(resource, helper_prefix)
        if k == "horizontalpodautoscaler":
            return cls._generate_hpa_template(resource, helper_prefix)
        if k == "ingress":
            return cls._generate_ingress_template(resource, helper_prefix)
        if k == "serviceaccount":
            return cls._generate_serviceaccount_template(resource, helper_prefix)

        # Fallback for ConfigMap, Secret, PVC, RBAC, etc.
        return cls._generate_generic_template(resource, helper_prefix)

    @classmethod
    def _generate_deployment_template(
        cls,
        resource: DiscoveredResource,
        prefix: str,
        has_hpa: bool,
    ) -> str:
        doc = dict(resource.raw_doc)
        pod_template = doc.get("spec", {}).get("template", {})
        containers = pod_template.get("spec", {}).get("containers", [])
        c0 = containers[0] if containers else {}

        ports = c0.get("ports", [])
        port_num = ports[0].get("containerPort", 80) if ports else 80
        port_name = ports[0].get("name", "http") if ports else "http"

        hpa_check = ""
        if has_hpa:
            hpa_check = """  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}"""
        else:
            hpa_check = "  replicas: {{ .Values.replicaCount }}"

        return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ include "{prefix}.fullname" . }}}}
  labels:
    {{{{- include "{prefix}.labels" . | nindent 4 }}}}
spec:
{hpa_check}
  selector:
    matchLabels:
      {{{{- include "{prefix}.selectorLabels" . | nindent 6 }}}}
  template:
    metadata:
      labels:
        {{{{- include "{prefix}.selectorLabels" . | nindent 8 }}}}
    spec:
      {{{{- with .Values.imagePullSecrets }}}}
      imagePullSecrets:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      serviceAccountName: {{{{ include "{prefix}.serviceAccountName" . }}}}
      containers:
        - name: {{{{ .Chart.Name }}}}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag | default .Chart.AppVersion }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          ports:
            - name: {port_name}
              containerPort: {port_num}
              protocol: TCP
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
"""

    @classmethod
    def _generate_service_template(cls, resource: DiscoveredResource, prefix: str) -> str:
        ports = resource.spec.get("ports", [])
        p0 = ports[0] if ports else {}
        target_port = p0.get("targetPort", "http")

        return f"""apiVersion: v1
kind: Service
metadata:
  name: {{{{ include "{prefix}.fullname" . }}}}
  labels:
    {{{{- include "{prefix}.labels" . | nindent 4 }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: {target_port}
      protocol: TCP
      name: http
  selector:
    {{{{- include "{prefix}.selectorLabels" . | nindent 4 }}}}
"""

    @classmethod
    def _generate_hpa_template(cls, resource: DiscoveredResource, prefix: str) -> str:
        target_ref = resource.spec.get("scaleTargetRef", {})
        target_kind = target_ref.get("kind", "Deployment")

        return f"""{{{{- if .Values.autoscaling.enabled }}}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{{{ include "{prefix}.fullname" . }}}}
  labels:
    {{{{- include "{prefix}.labels" . | nindent 4 }}}}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: {target_kind}
    name: {{{{ include "{prefix}.fullname" . }}}}
  minReplicas: {{{{ .Values.autoscaling.minReplicas }}}}
  maxReplicas: {{{{ .Values.autoscaling.maxReplicas }}}}
  metrics:
    {{{{- if .Values.autoscaling.targetCPUUtilizationPercentage }}}}
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}
    {{{{- end }}}}
    {{{{- if .Values.autoscaling.targetMemoryUtilizationPercentage }}}}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetMemoryUtilizationPercentage }}}}
    {{{{- end }}}}
{{{{- end }}}}
"""

    @classmethod
    def _generate_ingress_template(cls, resource: DiscoveredResource, prefix: str) -> str:
        return f"""{{{{- if .Values.ingress.enabled -}}}}
{{{{- $fullName := include "{prefix}.fullname" . -}}}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{{{ $fullName }}}}
  labels:
    {{{{- include "{prefix}.labels" . | nindent 4 }}}}
  {{{{- with .Values.ingress.annotations }}}}
  annotations:
    {{{{- toYaml . | nindent 4 }}}}
  {{{{- end }}}}
spec:
  {{{{- if .Values.ingress.className }}}}
  ingressClassName: {{{{ .Values.ingress.className }}}}
  {{{{- end }}}}
  rules:
    {{{{- range .Values.ingress.hosts }}}}
    - host: {{{{ .host | quote }}}}
      http:
        paths:
          {{{{- range .paths }}}}
          - path: {{{{ .path }}}}
            pathType: {{{{ .pathType }}}}
            backend:
              service:
                name: {{{{ $fullName }}}}
                port:
                  number: {{{{ $.Values.service.port }}}}
          {{{{- end }}}}
    {{{{- end }}}}
{{{{- end }}}}
"""

    @classmethod
    def _generate_serviceaccount_template(cls, resource: DiscoveredResource, prefix: str) -> str:
        return f"""{{{{- if .Values.serviceAccount.create -}}}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{{{ include "{prefix}.serviceAccountName" . }}}}
  labels:
    {{{{- include "{prefix}.labels" . | nindent 4 }}}}
  {{{{- with .Values.serviceAccount.annotations }}}}
  annotations:
    {{{{- toYaml . | nindent 4 }}}}
  {{{{- end }}}}
{{{{- end }}}}
"""

    @classmethod
    def _generate_generic_template(cls, resource: DiscoveredResource, prefix: str) -> str:
        doc = dict(resource.raw_doc)
        kind = resource.kind
        clean_name = cls._sanitize_name(resource.name)

        # Standardize metadata
        header = f"""apiVersion: {resource.api_version}
kind: {kind}
metadata:
  name: {{{{ include "{prefix}.fullname" . }}}}-{clean_name}
  labels:
    {{{{- include "{prefix}.labels" . | nindent 4 }}}}
"""
        yaml_str = yaml.dump(doc, sort_keys=False)
        # Strip metadata from existing YAML and re-attach standardized header
        if "metadata:" in yaml_str:
            lines = yaml_str.splitlines()
            body_lines: list[str] = []
            in_meta = False
            for line in lines:
                if line.startswith("metadata:"):
                    in_meta = True
                    continue
                if in_meta:
                    if line.startswith(" ") or line.startswith("\t"):
                        continue
                    else:
                        in_meta = False
                if not in_meta and not line.startswith("apiVersion:") and not line.startswith("kind:"):
                    body_lines.append(line)
            return header + "\n".join(body_lines) + "\n"
        return header + yaml_str
