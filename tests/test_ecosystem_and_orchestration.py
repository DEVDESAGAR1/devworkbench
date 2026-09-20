"""Tests for ecosystem tool integration, execution transparency, conversion, and cleanup engines."""

import json
from pathlib import Path

from click.testing import CliRunner

from devworkbench.capabilities.model import CapabilityType
from devworkbench.capabilities.registry import CapabilityRegistry
from devworkbench.capabilities.resolver import CapabilityResolver
from devworkbench.cleaner import ManifestCleaner
from devworkbench.cli import main
from devworkbench.converter import HelmConverter
from devworkbench.execution import (
    CommandRunner,
    redact_secrets_from_args,
    redact_secrets_from_string,
)
from devworkbench.models import CheckCoverage, ResourceAction
from devworkbench.scanner import Scanner


def test_command_runner_redaction():
    """Verify secrets (passwords, tokens, AWS keys, bearer tokens) are safely redacted."""
    raw_text = "curl -H 'Authorization: bearer secret_token_123' --password supersecret AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI"
    redacted = redact_secrets_from_string(raw_text)
    assert "secret_token_123" not in redacted
    assert "supersecret" not in redacted
    assert "wJalrXUtnFEMI" not in redacted

    raw_args = ["kubectl", "--token", "secret123", "--password=mypass", "get", "pods"]
    redacted_args = redact_secrets_from_args(raw_args)
    assert "secret123" not in redacted_args
    assert "mypass" not in " ".join(redacted_args)


def test_command_runner_execution_telemetry(tmp_path: Path):
    """Verify CommandRunner executes commands and captures duration, exit code, and command details."""
    exec_res = CommandRunner.run_command(
        executable="python",
        args=["-c", "print('hello devworkbench')"],
        technology="Python",
        capability="test_cap",
        provider_type="native",
        provider_name="python",
        cwd=tmp_path,
        timeout_seconds=5.0,
    )
    assert exec_res.status == "PASS"
    assert exec_res.exit_code == 0
    assert "hello devworkbench" in exec_res.stdout
    assert exec_res.duration_ms >= 0


def test_command_runner_unavailable_executable(tmp_path: Path):
    """Verify CommandRunner cleanly reports UNAVAILABLE for non-existent tools without crashing."""
    exec_res = CommandRunner.run_command(
        executable="non_existent_tool_xyz_999",
        args=["--help"],
        technology="Kubernetes",
        capability="k8s_clean",
        provider_type="opensource",
        provider_name="non-existent",
        cwd=tmp_path,
    )
    assert exec_res.status == "UNAVAILABLE"
    assert exec_res.exit_code is None
    assert "not found" in (exec_res.unavailable_reason or "")


def test_capability_registry_and_resolver():
    """Verify CapabilityRegistry has all ecosystem capabilities and resolver respects priorities."""
    registry = CapabilityRegistry()
    resolver = CapabilityResolver(registry=registry)

    # Check that Black, kubeconform, helmify, kubectl-neat are registered
    k8s_clean_providers = registry.get_providers_for_capability(CapabilityType.KUBERNETES_CLEANUP)
    assert any(p.name == "kubectl-neat" for p in k8s_clean_providers)
    assert any(p.name == "devworkbench-k8s-clean" for p in k8s_clean_providers)

    k8s_helm_providers = registry.get_providers_for_capability(CapabilityType.KUBERNETES_TO_HELM)
    assert any(p.name == "helmify" for p in k8s_helm_providers)
    assert any(p.name == "devworkbench-to-helm" for p in k8s_helm_providers)

    # Resolution
    res = resolver.resolve(CapabilityType.KUBERNETES_CLEANUP)
    assert res.capability == CapabilityType.KUBERNETES_CLEANUP
    assert res.selected_provider is not None


def test_scanner_aggregates_executions_and_coverage(tmp_path: Path):
    """Verify Scanner captures executions and computes CheckCoverage."""
    py_file = tmp_path / "valid.py"
    py_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    scanner = Scanner()
    result = scanner.scan(str(tmp_path))

    assert len(result.executions) > 0
    assert result.summary.coverage in [CheckCoverage.FULL, CheckCoverage.PARTIAL, CheckCoverage.DEGRADED]
    assert result.summary.checks_passed >= 1


def test_manifest_cleaner_internal_fallback(tmp_path: Path):
    """Verify ManifestCleaner removes runtime metadata and status fields using internal engine."""
    dirty_yaml = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: sample-app
  namespace: default
  uid: a1b2c3d4-e5f6-7890-1234-567890abcdef
  resourceVersion: "1234567"
  generation: 4
  creationTimestamp: "2026-01-01T00:00:00Z"
  managedFields:
    - manager: kube-controller-manager
      operation: Update
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: nginx
          image: nginx:1.21
status:
  availableReplicas: 3
  readyReplicas: 3
"""
    cleaned_res = ManifestCleaner.clean(
        content_or_path=dirty_yaml,
        use_external_tool=False,
    )
    assert cleaned_res.validation_passed is True
    assert "uid:" not in cleaned_res.cleaned_yaml
    assert "resourceVersion:" not in cleaned_res.cleaned_yaml
    assert "generation:" not in cleaned_res.cleaned_yaml
    assert "creationTimestamp:" not in cleaned_res.cleaned_yaml
    assert "managedFields:" not in cleaned_res.cleaned_yaml
    assert "status:" not in cleaned_res.cleaned_yaml
    assert "replicas: 3" in cleaned_res.cleaned_yaml
    assert cleaned_res.diff != ""


def test_manifest_cleaner_file_write(tmp_path: Path):
    """Verify ManifestCleaner write option writes cleaned manifest directly."""
    k8s_file = tmp_path / "dirty.yaml"
    dirty_yaml = """apiVersion: v1
kind: Service
metadata:
  name: my-service
  uid: 9876-abcd
  resourceVersion: "999"
spec:
  ports:
    - port: 80
status:
  loadBalancer: {}
"""
    k8s_file.write_text(dirty_yaml)

    out_file = tmp_path / "cleaned.yaml"
    res = ManifestCleaner.clean(
        content_or_path=k8s_file,
        write_output_path=out_file,
        use_external_tool=False,
    )
    assert res.written is True
    assert out_file.is_file()
    saved_content = out_file.read_text()
    assert "uid" not in saved_content
    assert "my-service" in saved_content


def test_helm_converter_planning_and_reconciliation(tmp_path: Path):
    """Verify HelmConverter plans resource actions (CREATE/UPDATE/KEEP) and generates chart."""
    dep_file = tmp_path / "deployment.yaml"
    dep_file.write_text("""apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: order
          image: order-svc:1.0
""")

    out_dir = tmp_path / "charts"

    # 1. Dry-run conversion
    dry_res = HelmConverter.convert(
        input_paths=[dep_file],
        target_dir=out_dir,
        chart_name="order-chart",
        dry_run=True,
    )
    assert dry_res.status == "dry_run"
    assert len(dry_res.plan.resource_items) == 1
    assert dry_res.plan.resource_items[0].action == ResourceAction.CREATE
    assert not (out_dir / "order-chart").exists()

    # 2. Real conversion
    real_res = HelmConverter.convert(
        input_paths=[dep_file],
        target_dir=out_dir,
        chart_name="order-chart",
        dry_run=False,
    )
    assert real_res.status == "success"
    chart_root = out_dir / "order-chart"
    assert (chart_root / "Chart.yaml").is_file()
    assert (chart_root / "values.yaml").is_file()
    assert (chart_root / "templates" / "_helpers.tpl").is_file()
    assert (chart_root / "templates" / "deployment-order-service.yaml").is_file()


def test_cli_clean_command(tmp_path: Path):
    """Verify `devworkbench clean` CLI command."""
    k8s_file = tmp_path / "app.yaml"
    k8s_file.write_text("""apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  uid: dummy-uid-123
data:
  ENV: production
status:
  ready: true
""")

    runner = CliRunner()
    # 1. Human / YAML output
    result = runner.invoke(main, ["clean", str(k8s_file), "--format", "diff"])
    assert result.exit_code == 0
    assert "-  uid: dummy-uid-123" in result.output

    # 2. JSON output
    json_res = runner.invoke(main, ["clean", str(k8s_file), "--json"])
    assert json_res.exit_code == 0
    data = json.loads(json_res.output)
    assert "cleaned_yaml" in data
    assert "dummy-uid-123" not in data["cleaned_yaml"]


def test_cli_convert_command(tmp_path: Path):
    """Verify `devworkbench convert` CLI command."""
    k8s_file = tmp_path / "svc.yaml"
    k8s_file.write_text("""apiVersion: v1
kind: Service
metadata:
  name: payment-svc
spec:
  ports:
    - port: 8080
""")

    charts_dir = tmp_path / "output_charts"
    runner = CliRunner()

    # 1. Dry run
    res_dry = runner.invoke(
        main,
        ["convert", str(k8s_file), "--to", "helm", "--output-dir", str(charts_dir), "--name", "payment-chart", "--dry-run"],
    )
    assert res_dry.exit_code == 0
    assert "Conversion Plan" in res_dry.output or "payment-chart" in res_dry.output
    assert not (charts_dir / "payment-chart").exists()

    # 2. Real execution
    res_real = runner.invoke(
        main,
        ["convert", str(k8s_file), "--to", "helm", "--output-dir", str(charts_dir), "--name", "payment-chart"],
    )
    assert res_real.exit_code == 0
    assert (charts_dir / "payment-chart" / "Chart.yaml").exists()
