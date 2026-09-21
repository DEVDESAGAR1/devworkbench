"""Comprehensive tests for Milestone 9: Mandatory Helmify Integration as an Open Source Provider."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from devworkbench.adapters.helmify_adapter import HelmifyAdapter, HelmifyResult
from devworkbench.capabilities.model import CapabilityType, ToolPriority
from devworkbench.capabilities.registry import CapabilityRegistry
from devworkbench.capabilities.resolver import CapabilityResolver
from devworkbench.cli import main
from devworkbench.migration.detector import ManifestDetector
from devworkbench.migration.generator import HelmGenerator
from devworkbench.migration.models import DiscoveredResource, ReferencePattern
from devworkbench.models import CommandExecution, Technology

# ============================================================================
# 1. CAPABILITY REGISTRATION & HIERARCHY TESTS
# ============================================================================


def test_helmify_registered_in_capability_registry():
    """Verify Helmify is registered as OPENSOURCE (Priority 2) for both Helm and Kubernetes."""
    registry = CapabilityRegistry()

    # Under Technology.HELM
    helm_providers = registry.get_providers_for_technology(Technology.HELM)
    helmify_helm = next((p for p in helm_providers if p.name == "helmify"), None)
    assert helmify_helm is not None
    assert helmify_helm.priority == ToolPriority.OPENSOURCE
    assert helmify_helm.capability == CapabilityType.HELM_CONVERSION

    # Under Technology.KUBERNETES
    k8s_providers = registry.get_providers_for_technology(Technology.KUBERNETES)
    helmify_k8s = next((p for p in k8s_providers if p.name == "helmify"), None)
    assert helmify_k8s is not None
    assert helmify_k8s.priority == ToolPriority.OPENSOURCE
    assert helmify_k8s.capability == CapabilityType.KUBERNETES_TO_HELM


def test_kubernetes_to_helm_provider_hierarchy_order():
    """Verify provider order for KUBERNETES_TO_HELM: 1. Native -> 2. OpenSource (Helmify) -> 3. DevWorkBench -> 4. Manual."""
    registry = CapabilityRegistry()
    providers = registry.get_providers_for_capability(CapabilityType.KUBERNETES_TO_HELM)

    priorities = [int(p.priority) for p in providers]
    assert priorities == sorted(priorities), "Providers must be sorted strictly by ToolPriority (1 to 4)"

    # Helmify is OPENSOURCE (Priority 2)
    helmify_p = next(p for p in providers if p.name == "helmify")
    assert helmify_p.priority == ToolPriority.OPENSOURCE

    # DevWorkBench fallback is DEVWORKBENCH (Priority 3)
    dwb_p = next(p for p in providers if p.name == "devworkbench-to-helm")
    assert dwb_p.priority == ToolPriority.DEVWORKBENCH


def test_resolver_selects_helmify_when_available():
    """Verify CapabilityResolver selects Helmify when its binary is available."""
    registry = CapabilityRegistry()
    resolver = CapabilityResolver(registry=registry)

    with patch.object(registry.providers[0].__class__, "is_available", new_callable=lambda: property(lambda self: True)):
        # Patch specifically helmify provider to be available
        for p in registry.providers:
            if p.name == "helmify" and p.capability == CapabilityType.KUBERNETES_TO_HELM:
                p.is_available_fn = lambda: True

        result = resolver.resolve(CapabilityType.KUBERNETES_TO_HELM)
        assert result.selected_provider is not None
        assert result.selected_provider.name == "helmify"
        assert result.priority == ToolPriority.OPENSOURCE


def test_resolver_falls_back_to_devworkbench_when_helmify_missing():
    """Verify CapabilityResolver gracefully falls back to DevWorkBench (Priority 3) when Helmify is missing."""
    registry = CapabilityRegistry()
    resolver = CapabilityResolver(registry=registry)

    # Force all opensource to be unavailable
    for p in registry.providers:
        if p.name in ("helmify", "chartify"):
            p.is_available_fn = lambda: False

    result = resolver.resolve(CapabilityType.KUBERNETES_TO_HELM)
    assert result.selected_provider is not None
    assert result.selected_provider.name == "devworkbench-to-helm"
    assert result.priority == ToolPriority.DEVWORKBENCH
    assert "fallback" in result.reason.lower() or "active as verified fallback" in result.reason.lower()


# ============================================================================
# 2. ADAPTER UNIT TESTS
# ============================================================================


def test_helmify_adapter_metadata_and_can_handle():
    """Verify HelmifyAdapter properties and technology handling."""
    adapter = HelmifyAdapter()
    assert adapter.name == "helmify"
    assert adapter.technology == Technology.KUBERNETES

    det_k8s = MagicMock()
    det_k8s.technology = Technology.KUBERNETES
    assert adapter.can_handle(det_k8s) is True

    det_helm = MagicMock()
    det_helm.technology = Technology.HELM
    assert adapter.can_handle(det_helm) is True

    det_py = MagicMock()
    det_py.technology = Technology.PYTHON
    assert adapter.can_handle(det_py) is False


def test_helmify_adapter_is_available_when_not_installed():
    """Verify is_available returns False and a valid ToolWarning without errors."""
    adapter = HelmifyAdapter()
    with patch.object(adapter, "find_tool", return_value=None):
        avail, warning = adapter.is_available()
        assert avail is False
        assert warning is not None
        assert warning.tool_name == "helmify"
        assert warning.technology == Technology.KUBERNETES
        assert "arttor/helmify" in warning.install_hint


def test_helmify_adapter_convert_manifests_unavailable(tmp_path: Path):
    """Verify convert_manifests returns clean failure result when binary is unavailable."""
    adapter = HelmifyAdapter()
    with patch.object(adapter, "is_available", return_value=(False, None)):
        resource = DiscoveredResource(
            api_version="apps/v1",
            kind="Deployment",
            name="demo-app",
            namespace="default",
            source_file=str(tmp_path / "dep.yaml"),
            source_doc_index=0,
            raw_doc={"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "demo-app"}},
        )
        res = adapter.convert_manifests([resource], "demo-chart")
        assert res.success is False
        assert res.execution.status == "UNAVAILABLE"
        assert "Deployment/demo-app" in res.unsupported_resources


def test_helmify_adapter_handles_nonzero_exit(tmp_path: Path):
    """Verify convert_manifests handles non-zero exit from helmify cleanly."""
    adapter = HelmifyAdapter()
    dummy_exec = CommandExecution(
        technology="Kubernetes",
        capability="kubernetes_to_helm",
        provider_type="opensource",
        provider_name="helmify",
        executable="helmify",
        args=["demo-chart"],
        command="helmify demo-chart",
        cwd=str(tmp_path),
        status="FAIL",
        exit_code=1,
        stdout="",
        stderr="helmify: parse error in stdin",
        duration_ms=45.0,
        error_message="helmify: parse error in stdin",
    )

    with patch.object(adapter, "is_available", return_value=(True, None)), \
         patch("devworkbench.execution.CommandRunner.run_command", return_value=dummy_exec):
        resource = DiscoveredResource(
            api_version="apps/v1",
            kind="Deployment",
            name="demo-app",
            namespace="default",
            source_file=str(tmp_path / "dep.yaml"),
            source_doc_index=0,
            raw_doc={"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "demo-app"}},
        )
        res = adapter.convert_manifests([resource], "demo-chart")
        assert res.success is False
        assert "parse error" in (res.error_message or "")
        assert "Deployment/demo-app" in res.unsupported_resources


# ============================================================================
# 3. HELM GENERATOR ORCHESTRATION & FALLBACK TESTS
# ============================================================================


def test_plan_reflects_helmify_when_available(tmp_path: Path):
    """Verify HelmGenerator.plan designates Helmify (OPEN_SOURCE) when available."""
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "dep.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: cart-service
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: app
          image: cart:1.0
""",
        encoding="utf-8",
    )
    resources = ManifestDetector.discover_directory(k8s_dir)

    with patch("devworkbench.capabilities.registry._is_binary_available", return_value=True):
        plan = HelmGenerator.plan(resources, tmp_path / "out", "cart-service")
        assert len(plan.planned_items) == 1
        item = plan.planned_items[0]
        assert item.provider == "Helmify"
        assert item.priority == "OPEN_SOURCE"
        assert "Open Source Helmify" in item.reason


def test_plan_reflects_devworkbench_fallback_when_helmify_unavailable(tmp_path: Path):
    """Verify HelmGenerator.plan designates DevWorkBench fallback when Helmify is missing."""
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "dep.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: cart-service
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: app
          image: cart:1.0
""",
        encoding="utf-8",
    )
    resources = ManifestDetector.discover_directory(k8s_dir)

    with patch("devworkbench.capabilities.registry._is_binary_available", return_value=False):
        plan = HelmGenerator.plan(resources, tmp_path / "out", "cart-service")
        assert len(plan.planned_items) == 1
        item = plan.planned_items[0]
        assert item.provider == "DEVWORKBENCH"
        assert item.priority == "DEVWORKBENCH"
        assert "DevWorkBench" in item.reason


def test_generate_orchestrates_helmify_and_preserves_hpa(tmp_path: Path):
    """Verify generate delegates to Helmify for workloads while DevWorkBench supplements HPA autoscaling/v2."""
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()

    (k8s_dir / "deployment.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-svc
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: payment
          image: payment:2.1.0
""",
        encoding="utf-8",
    )

    (k8s_dir / "hpa.yaml").write_text(
        """apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: payment-svc
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payment-svc
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 75
""",
        encoding="utf-8",
    )

    resources = ManifestDetector.discover_directory(k8s_dir)
    target_chart_dir = tmp_path / "payment-chart"

    # Mock Helmify converting Deployment, but omitting HPA
    helmify_res = HelmifyResult(
        success=True,
        execution=CommandExecution(
            technology="Kubernetes",
            capability="kubernetes_to_helm",
            provider_type="opensource",
            provider_name="helmify",
            executable="helmify",
            args=["payment-chart"],
            command="helmify payment-chart",
            cwd=str(tmp_path),
            status="PASS",
            exit_code=0,
            stdout="Chart generated",
            stderr="",
            duration_ms=35.0,
        ),
        templates={
            "deployment.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "payment-chart.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
        - name: payment
          image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
""",
            "_helpers.tpl": """{{- define "payment-chart.fullname" -}}payment-chart{{- end -}}""",
        },
        values={
            "replicaCount": 3,
            "image": {"repository": "payment", "tag": "2.1.0"},
        },
        chart_yaml={"name": "payment-chart", "version": "0.1.0"},
        converted_resources=["Deployment/payment-svc"],
        unsupported_resources=["HorizontalPodAutoscaler/payment-svc"],
    )

    with patch("devworkbench.capabilities.registry._is_binary_available", return_value=True), \
         patch("devworkbench.adapters.helmify_adapter.HelmifyAdapter.convert_manifests", return_value=helmify_res):
        result = HelmGenerator.generate(
            resources=resources,
            target_dir=target_chart_dir,
            chart_name="payment-chart",
        )

        assert result.status == "success"
        chart_path = Path(result.target_dir)

        # 1. Both templates exist
        assert (chart_path / "templates" / "deployment.yaml").is_file()
        assert (chart_path / "templates" / "hpa.yaml").is_file()

        # 2. Deployment was gated with autoscaling.enabled because HPA exists
        dep_content = (chart_path / "templates" / "deployment.yaml").read_text(encoding="utf-8")
        assert "if not .Values.autoscaling.enabled" in dep_content

        # 3. HPA uses autoscaling/v2 and targetCPUUtilizationPercentage
        hpa_content = (chart_path / "templates" / "hpa.yaml").read_text(encoding="utf-8")
        assert "autoscaling/v2" in hpa_content
        assert ".Values.autoscaling.targetCPUUtilizationPercentage" in hpa_content

        # 4. Values contain both Helmify's values and DevWorkBench's autoscaling block
        values_data = yaml.safe_load((chart_path / "values.yaml").read_text(encoding="utf-8"))
        assert values_data["image"]["repository"] == "payment"
        assert values_data["autoscaling"]["enabled"] is True
        assert values_data["autoscaling"]["targetCPUUtilizationPercentage"] == 75

        # 5. Traceability per resource: Deployment -> Helmify (OPEN_SOURCE), HPA -> DevWorkBench (DEVWORKBENCH)
        plan_items = {item.source_resource: item for item in result.plan.planned_items}
        assert plan_items["Deployment/payment-svc"].provider == "Helmify"
        assert plan_items["Deployment/payment-svc"].priority == "OPEN_SOURCE"

        assert plan_items["HorizontalPodAutoscaler/payment-svc"].provider == "DevWorkBench"
        assert plan_items["HorizontalPodAutoscaler/payment-svc"].priority == "DEVWORKBENCH"

        # 6. Execution telemetry contains helmify execution
        helmify_exec = next((e for e in result.validation_executions if e.provider_name == "helmify"), None)
        assert helmify_exec is not None
        assert helmify_exec.status == "PASS"


def test_generate_falls_back_when_helmify_execution_fails(tmp_path: Path):
    """Verify generate falls back to DevWorkBench for all templates when Helmify command fails."""
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "service.yaml").write_text(
        """apiVersion: v1
kind: Service
metadata:
  name: order-svc
spec:
  ports:
    - port: 80
      targetPort: 8080
""",
        encoding="utf-8",
    )

    resources = ManifestDetector.discover_directory(k8s_dir)
    target_chart_dir = tmp_path / "fallback-chart"

    failed_helmify_res = HelmifyResult(
        success=False,
        execution=CommandExecution(
            technology="Kubernetes",
            capability="kubernetes_to_helm",
            provider_type="opensource",
            provider_name="helmify",
            executable="helmify",
            args=["fallback-chart"],
            command="helmify fallback-chart",
            cwd=str(tmp_path),
            status="FAIL",
            exit_code=127,
            stdout="",
            stderr="helmify: crash in execution",
            duration_ms=12.0,
            error_message="helmify: crash in execution",
        ),
        error_message="helmify: crash in execution",
        unsupported_resources=["Service/order-svc"],
    )

    with patch("devworkbench.capabilities.registry._is_binary_available", return_value=True), \
         patch("devworkbench.adapters.helmify_adapter.HelmifyAdapter.convert_manifests", return_value=failed_helmify_res):
        result = HelmGenerator.generate(
            resources=resources,
            target_dir=target_chart_dir,
            chart_name="fallback-chart",
        )

        assert result.status == "success"
        chart_path = Path(result.target_dir)

        # Service was generated via fallback
        assert (chart_path / "templates" / "service.yaml").is_file()

        item = result.plan.planned_items[0]
        assert item.provider == "DevWorkBench"
        assert item.priority == "DEVWORKBENCH"
        assert "fallback" in item.reason.lower()


# ============================================================================
# 4. REFERENCE CONVENTIONS OVERLAY ON HELMIFY
# ============================================================================


def test_reference_conventions_overlay_on_helmify(tmp_path: Path):
    """Verify reference chart helper prefix and label schemes are integrated with Helmify."""
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "service.yaml").write_text(
        """apiVersion: v1
kind: Service
metadata:
  name: api-svc
spec:
  ports:
    - port: 8080
""",
        encoding="utf-8",
    )
    resources = ManifestDetector.discover_directory(k8s_dir)

    reference = ReferencePattern(
        name="corporate-standard",
        chart_name="corp-base",
        helper_prefix="corp-base",
        label_scheme={"organization": "acme-corp", "tier": "backend"},
        values_hierarchy={"monitoring": {"prometheus": {"enabled": True}}},
    )

    target_dir = tmp_path / "overlay-chart"

    helmify_res = HelmifyResult(
        success=True,
        execution=CommandExecution(
            technology="Kubernetes",
            capability="kubernetes_to_helm",
            provider_type="opensource",
            provider_name="helmify",
            executable="helmify",
            args=["overlay-chart"],
            command="helmify overlay-chart",
            cwd=str(tmp_path),
            status="PASS",
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=20.0,
        ),
        templates={
            "service.yaml": """apiVersion: v1
kind: Service
metadata:
  name: {{ include "overlay-chart.fullname" . }}
spec:
  ports:
    - port: 8080
""",
        },
        values={"service": {"port": 8080}},
        chart_yaml={"name": "overlay-chart", "version": "0.1.0"},
        converted_resources=["Service/api-svc"],
    )

    with patch("devworkbench.capabilities.registry._is_binary_available", return_value=True), \
         patch("devworkbench.adapters.helmify_adapter.HelmifyAdapter.convert_manifests", return_value=helmify_res):
        result = HelmGenerator.generate(
            resources=resources,
            target_dir=target_dir,
            chart_name="overlay-chart",
            reference=reference,
        )

        chart_path = Path(result.target_dir)

        # Helpers file defines both corp-base and alias for overlay-chart
        helpers_content = (chart_path / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
        assert 'define "corp-base.name"' in helpers_content
        assert 'define "overlay-chart.name"' in helpers_content

        # Values contain merged reference hierarchy
        values_data = yaml.safe_load((chart_path / "values.yaml").read_text(encoding="utf-8"))
        assert values_data["monitoring"]["prometheus"]["enabled"] is True
        assert values_data["service"]["port"] == 8080


# ============================================================================
# 5. CLI --provider PREFERENCE TESTS
# ============================================================================


def test_cli_migrate_with_provider_flag(tmp_path: Path):
    """Verify devworkbench migrate --provider devworkbench forces DevWorkBench provider."""
    runner = CliRunner()
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "dep.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: web
          image: web:1.0
""",
        encoding="utf-8",
    )
    output_dir = tmp_path / "cli-provider-out"

    result = runner.invoke(
        main,
        [
            "migrate",
            str(k8s_dir),
            "--to",
            "helm",
            "--provider",
            "devworkbench",
            "--output",
            str(output_dir),
            "--name",
            "web-app",
        ],
    )

    assert result.exit_code == 0
    assert "Migration Completed Successfully" in result.output
    assert "Provider:" in result.output
    assert (output_dir / "Chart.yaml").is_file()


def test_cli_migrate_json_includes_provider_and_priority(tmp_path: Path):
    """Verify --json output includes provider and priority fields for each plan item."""
    runner = CliRunner()
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "dep.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: backend
          image: backend:1.0
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        [
            "migrate",
            str(k8s_dir),
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "plan" in data
    items = data["plan"]["planned_items"]
    assert len(items) == 1
    assert "provider" in items[0]
    assert "priority" in items[0]
    assert "reason" in items[0]
