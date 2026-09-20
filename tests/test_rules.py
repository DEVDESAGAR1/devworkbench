"""Unit tests for DevOps best-practice rules."""

from pathlib import Path

from devworkbench.models import FileCategory, FileDetection, Technology
from devworkbench.rules.registry import RuleRegistry


def test_k8s_resource_limits_and_latest_tag_rules(tmp_path: Path) -> None:
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      containers:
      - name: api
        image: api:latest
""")
    det = FileDetection(
        path=str(manifest),
        relative_path="deployment.yaml",
        technology=Technology.KUBERNETES,
        category=FileCategory.DEVOPS,
    )

    registry = RuleRegistry()
    diags = registry.evaluate_rules(manifest, det)

    rule_ids = {d.rule for d in diags}
    assert "K8S001" in rule_ids  # Missing resources
    assert "K8S003" in rule_ids  # Uses :latest tag


def test_openshift_insecure_route_rule(tmp_path: Path) -> None:
    route_file = tmp_path / "route.yaml"
    route_file.write_text("""apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: my-route
spec:
  to:
    kind: Service
    name: svc
""")
    det = FileDetection(
        path=str(route_file),
        relative_path="route.yaml",
        technology=Technology.OPENSHIFT,
        category=FileCategory.DEVOPS,
    )

    registry = RuleRegistry()
    diags = registry.evaluate_rules(route_file, det)

    assert any(d.rule == "OPENSHIFT001" for d in diags)


def test_helm_chart_metadata_rule(tmp_path: Path) -> None:
    chart_file = tmp_path / "Chart.yaml"
    chart_file.write_text("""apiVersion: v2
name: payment-service
# missing 'version'
""")
    det = FileDetection(
        path=str(chart_file),
        relative_path="Chart.yaml",
        technology=Technology.HELM,
        category=FileCategory.DEVOPS,
    )

    registry = RuleRegistry()
    diags = registry.evaluate_rules(chart_file, det)

    assert any(d.rule == "HELM001" for d in diags)
