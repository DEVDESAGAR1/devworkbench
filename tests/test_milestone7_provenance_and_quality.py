"""Tests for Milestone 7: Production-Grade DevOps Rules, Diagnostics & Analysis Quality."""

import hashlib
import json
from pathlib import Path
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.deduplication import DiagnosticDeduplicator
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
)
from devworkbench.rules.registry import RuleRegistry
from devworkbench.rules.kubernetes import K8sPrivilegedContainerRule, K8sMissingProbesRule
from devworkbench.rules.docker import DockerLatestImageRule
from devworkbench.rules.terraform import TerraformHardcodedSecretRule
from devworkbench.rules.helm import HelmChartMaintainersRule
from devworkbench.scanner import Scanner


def test_diagnostic_provenance_fields():
    """Verify Diagnostic model serialization with provenance fields."""
    diag = Diagnostic(
        path="deploy.yaml",
        line=10,
        severity=DiagnosticSeverity.WARNING,
        rule="K8S001",
        message="Container is missing CPU/memory limits",
        source="devworkbench",
        category=DiagnosticCategory.BEST_PRACTICE,
        provider="devworkbench",
        provider_priority=3,
        provider_type="devworkbench",
        rule_origin="DevWorkBench: Kubernetes Rules",
        documentation_url="https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/",
        contributing_sources=["kube-linter"],
    )

    d_dict = diag.to_dict()
    assert d_dict["provider"] == "devworkbench"
    assert d_dict["provider_priority"] == 3
    assert d_dict["provider_type"] == "devworkbench"
    assert d_dict["rule_origin"] == "DevWorkBench: Kubernetes Rules"
    assert "https://kubernetes.io" in d_dict["documentation_url"]
    assert d_dict["contributing_sources"] == ["kube-linter"]


def test_deduplication_records_contributing_sources():
    """Verify that deduplication retains highest fidelity diagnostic and records contributing sources."""
    d1 = Diagnostic(
        path="manifest.yaml",
        line=5,
        column=2,
        severity=DiagnosticSeverity.ERROR,
        rule="YAML001",
        message="YAML syntax error: unclosed quote",
        source="pyyaml",
        category=DiagnosticCategory.SYNTAX,
        provider="pyyaml",
        provider_priority=2,
        provider_type="opensource",
        rule_origin="OpenSource: PyYAML parser",
    )
    d2 = Diagnostic(
        path="manifest.yaml",
        line=5,
        column=5,
        severity=DiagnosticSeverity.ERROR,
        rule="syntax",
        message="YAML syntax error: unclosed quote",
        source="yamllint",
        category=DiagnosticCategory.SYNTAX,
        provider="yamllint",
        provider_priority=2,
        provider_type="opensource",
        rule_origin="OpenSource: yamllint",
    )

    deduped = DiagnosticDeduplicator.deduplicate([d1, d2])
    assert len(deduped) == 1
    retained = deduped[0]
    # Check that contributing sources were recorded
    assert len(retained.contributing_sources) >= 1
    assert any("pyyaml" in s for s in retained.contributing_sources)


def test_dockerfile_unpinned_base_image_rule(tmp_path: Path):
    """Verify DOCKER001 catches unpinned images like ubuntu:latest or node without tag."""
    df = tmp_path / "Dockerfile"
    df.write_text("FROM ubuntu:latest\nRUN apt-get update\n", encoding="utf-8")

    det = FileDetection(
        path=str(df),
        relative_path="Dockerfile",
        technology=Technology.DOCKERFILE,
        category="Container",
        confidence=1.0,
    )

    rule = DockerLatestImageRule()
    diags = rule.evaluate(df, df.read_text(encoding="utf-8"), det)
    assert len(diags) == 1
    assert diags[0].rule == "DOCKER001"
    assert diags[0].provider == "devworkbench"
    assert "DevWorkBench" in diags[0].rule_origin


def test_terraform_hardcoded_secret_rule(tmp_path: Path):
    """Verify TERRAFORM001 flags hardcoded API keys or cloud tokens."""
    tf = tmp_path / "main.tf"
    tf.write_text(
        'provider "aws" {\n  region = "us-east-1"\n  access_key = "AKIA1234567890EXAMPLE"\n}\n',
        encoding="utf-8",
    )

    det = FileDetection(
        path=str(tf),
        relative_path="main.tf",
        technology=Technology.TERRAFORM,
        category="IaC",
        confidence=1.0,
    )

    rule = TerraformHardcodedSecretRule()
    diags = rule.evaluate(tf, tf.read_text(encoding="utf-8"), det)
    assert len(diags) == 1
    assert diags[0].rule == "TERRAFORM001"
    assert diags[0].category == DiagnosticCategory.SECURITY
    assert diags[0].provider == "devworkbench"


def test_kubernetes_privileged_container_rule(tmp_path: Path):
    """Verify K8S002 detects privileged: true in pod specs."""
    k8s = tmp_path / "pod.yaml"
    k8s.write_text(
        """apiVersion: v1
kind: Pod
metadata:
  name: privileged-app
spec:
  containers:
  - name: app
    image: nginx:1.25.0
    securityContext:
      privileged: true
""",
        encoding="utf-8",
    )

    det = FileDetection(
        path=str(k8s),
        relative_path="pod.yaml",
        technology=Technology.KUBERNETES,
        category="Manifest",
        confidence=1.0,
    )

    rule = K8sPrivilegedContainerRule()
    diags = rule.evaluate(k8s, k8s.read_text(encoding="utf-8"), det)
    assert len(diags) == 1
    assert diags[0].rule == "K8S002"
    assert diags[0].severity == DiagnosticSeverity.ERROR


def test_kubernetes_missing_probes_rule(tmp_path: Path):
    """Verify K8S004 detects Deployment missing readinessProbe and livenessProbe."""
    k8s = tmp_path / "deployment.yaml"
    k8s.write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      - name: my-container
        image: nginx:1.25.0
""",
        encoding="utf-8",
    )

    det = FileDetection(
        path=str(k8s),
        relative_path="deployment.yaml",
        technology=Technology.KUBERNETES,
        category="Manifest",
        confidence=1.0,
    )

    rule = K8sMissingProbesRule()
    diags = rule.evaluate(k8s, k8s.read_text(encoding="utf-8"), det)
    assert len(diags) == 1
    assert diags[0].rule == "K8S004"
    assert diags[0].severity == DiagnosticSeverity.INFO


def test_helm_chart_maintainers_rule(tmp_path: Path):
    """Verify HELM002 detects Chart.yaml without maintainers or sources."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text(
        """apiVersion: v2
name: sample-chart
version: 0.1.0
description: A sample Helm chart
""",
        encoding="utf-8",
    )

    det = FileDetection(
        path=str(chart),
        relative_path="Chart.yaml",
        technology=Technology.HELM,
        category="Chart",
        confidence=1.0,
    )

    rule = HelmChartMaintainersRule()
    diags = rule.evaluate(chart, chart.read_text(encoding="utf-8"), det)
    assert len(diags) == 1
    assert diags[0].rule == "HELM002"
    assert diags[0].provider == "devworkbench"


def test_helm_go_template_not_falsely_flagged_by_yaml_adapter(tmp_path: Path):
    """Verify Helm Go-template constructs ({{ .Values... }}) in templates/ are not reported as YAML syntax errors."""
    chart_dir = tmp_path / "mychart"
    templates_dir = chart_dir / "templates"
    templates_dir.mkdir(parents=True)

    chart_yaml = chart_dir / "Chart.yaml"
    chart_yaml.write_text("apiVersion: v2\nname: mychart\nversion: 1.0.0\n", encoding="utf-8")

    tmpl_file = templates_dir / "deployment.yaml"
    tmpl_file.write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "mychart.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
""",
        encoding="utf-8",
    )

    scanner = Scanner()
    res = scanner.scan(str(chart_dir))
    # PyYAML should not fail on the template with a YAML syntax error
    yaml_syntax_errors = [
        d for d in res.diagnostics
        if d.category == DiagnosticCategory.SYNTAX and d.source == "pyyaml"
    ]
    assert len(yaml_syntax_errors) == 0


def test_rules_cli_human_and_json():
    """Verify 'devworkbench rules' and 'devworkbench rules --json' output rich metadata."""
    runner = CliRunner()
    
    # Human output
    res_human = runner.invoke(main, ["rules"])
    assert res_human.exit_code == 0
    assert "DevWorkBench - DevOps Best-Practice Rules" in res_human.output
    assert "K8S001" in res_human.output
    assert "DOCKER001" in res_human.output

    # JSON output
    res_json = runner.invoke(main, ["rules", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert isinstance(data, list)
    assert len(data) >= 10
    
    k8s001 = next(r for r in data if r["rule_id"] == "K8S001")
    assert k8s001["technology"] == "Kubernetes"
    assert "rationale" in k8s001
    assert "documentation_url" in k8s001
    assert "provider" in k8s001
    assert k8s001["provider_priority"] == 3


def test_scan_immutability_and_provenance(tmp_path: Path):
    """Verify scan leaves files unmodified and returns diagnostics with provenance."""
    sample = tmp_path / "app.py"
    content = "import os\nimport sys\ndef hello():\n  pass\n"
    sample.write_text(content, encoding="utf-8")
    h_before = hashlib.sha256(sample.read_bytes()).hexdigest()

    runner = CliRunner()
    res = runner.invoke(main, ["scan", str(sample), "--json"])
    assert res.exit_code == 0

    h_after = hashlib.sha256(sample.read_bytes()).hexdigest()
    assert h_before == h_after, "Scan must be strictly read-only and immutable"

    data = json.loads(res.output)
    assert "diagnostics" in data
