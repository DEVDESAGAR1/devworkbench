"""Comprehensive unit and integration tests for Milestone 9: Reference-Aware Helm Migration & Example Ingestion."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.migration.detector import ManifestDetector
from devworkbench.migration.examples import ExampleRegistry
from devworkbench.migration.generator import HelmGenerator
from devworkbench.migration.models import RelationshipStatus, RelationshipType
from devworkbench.migration.relationships import RelationshipAnalyzer
from devworkbench.migration.validator import MigrationValidator


def hash_directory(directory: Path) -> dict[str, str]:
    """Compute SHA-256 for all files in a directory."""
    hashes: dict[str, str] = {}
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            rel = p.relative_to(directory).as_posix()
            hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def k8s_input_dir(tmp_path: Path) -> Path:
    """Create a realistic multi-resource Kubernetes input directory."""
    k8s = tmp_path / "k8s"
    k8s.mkdir()

    # 1. Deployment referencing ConfigMap, Secret, ServiceAccount
    deployment_yaml = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: prod
  labels:
    app: order-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      serviceAccountName: order-sa
      containers:
        - name: app
          image: registry.example.com/services/order-api:2.4.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
              name: http
          envFrom:
            - configMapRef:
                name: order-config
            - secretRef:
                name: order-secrets
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
"""
    (k8s / "deployment.yaml").write_text(deployment_yaml, encoding="utf-8")

    # 2. Service matching deployment
    service_yaml = """apiVersion: v1
kind: Service
metadata:
  name: order-api
  labels:
    app: order-api
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8080
      protocol: TCP
      name: http
  selector:
    app: order-api
"""
    (k8s / "service.yaml").write_text(service_yaml, encoding="utf-8")

    # 3. HorizontalPodAutoscaler scaling order-api
    hpa_yaml = """apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 75
"""
    (k8s / "hpa.yaml").write_text(hpa_yaml, encoding="utf-8")

    # 4. Multi-doc YAML with ConfigMap and Secret
    config_yaml = """apiVersion: v1
kind: ConfigMap
metadata:
  name: order-config
data:
  LOG_LEVEL: info
  PORT: "8080"
---
apiVersion: v1
kind: Secret
metadata:
  name: order-secrets
type: Opaque
data:
  DB_PASSWORD: c3VwZXJzZWNyZXQ=
"""
    (k8s / "configs.yaml").write_text(config_yaml, encoding="utf-8")

    # 5. Nested rbac directory with ServiceAccount and Role
    rbac_dir = k8s / "rbac"
    rbac_dir.mkdir()
    sa_yaml = """apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-sa
"""
    (rbac_dir / "serviceaccount.yaml").write_text(sa_yaml, encoding="utf-8")

    # 6. Irrelevant / script files that should be ignored
    (k8s / "deploy.sh").write_text("#!/bin/bash\necho 'Do not execute me!'\n", encoding="utf-8")
    (k8s / "notes.txt").write_text("Deployment instructions\n", encoding="utf-8")

    return k8s


@pytest.fixture
def company_reference_chart(tmp_path: Path) -> Path:
    """Create a realistic reference Helm chart example with corporate standards."""
    chart_dir = tmp_path / "company-helm-example"
    chart_dir.mkdir()

    # Chart.yaml
    chart_meta = {
        "apiVersion": "v2",
        "name": "corporate-standard",
        "description": "Standard corporate Helm chart template",
        "type": "application",
        "version": "1.4.2",
        "appVersion": "2.0.0",
    }
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_meta), encoding="utf-8")

    # values.yaml with corporate conventions
    values_data = {
        "replicaCount": 2,
        "image": {
            "repository": "corp.registry.io/app",
            "pullPolicy": "Always",
            "tag": "stable",
        },
        "autoscaling": {
            "enabled": True,
            "minReplicas": 3,
            "maxReplicas": 12,
            "targetCPUUtilizationPercentage": 70,
        },
        "ingress": {
            "enabled": True,
            "className": "nginx",
        },
        "resources": {
            "limits": {"cpu": "1000m", "memory": "1Gi"},
            "requests": {"cpu": "200m", "memory": "256Mi"},
        },
    }
    (chart_dir / "values.yaml").write_text(yaml.dump(values_data), encoding="utf-8")

    # templates/
    templates_dir = chart_dir / "templates"
    templates_dir.mkdir()

    # _helpers.tpl with custom corporate helper prefix
    helpers_tpl = """{{/*
Corporate standard helpers
*/}}
{{- define "corp-standard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "corp-standard.fullname" -}}
{{- default .Chart.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "corp-standard.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ include "corp-standard.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "corp-standard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "corp-standard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
"""
    (templates_dir / "_helpers.tpl").write_text(helpers_tpl, encoding="utf-8")

    # Templates in reference: Deployment, Service, HPA, Ingress, ConfigMap
    (templates_dir / "deployment.yaml").write_text("# Corporate deployment template\nkind: Deployment\n", encoding="utf-8")
    (templates_dir / "service.yaml").write_text("# Corporate service template\nkind: Service\n", encoding="utf-8")
    (templates_dir / "hpa.yaml").write_text("# Corporate HPA template\nkind: HorizontalPodAutoscaler\n", encoding="utf-8")
    (templates_dir / "ingress.yaml").write_text("# Corporate Ingress template\nkind: Ingress\n", encoding="utf-8")
    (templates_dir / "configmap.yaml").write_text("# Corporate ConfigMap template\nkind: ConfigMap\n", encoding="utf-8")

    return chart_dir


# ============================================================================
# 1. DISCOVERY & PARSING TESTS
# ============================================================================


def test_discovery_nested_directories_and_multidoc(k8s_input_dir: Path):
    """Verify recursive directory discovery, nested manifests, and multi-doc parsing."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)

    kinds = [r.kind for r in resources]
    names = [r.name for r in resources]

    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "HorizontalPodAutoscaler" in kinds
    assert "ConfigMap" in kinds
    assert "Secret" in kinds
    assert "ServiceAccount" in kinds

    assert "order-api" in names
    assert "order-api-hpa" in names
    assert "order-config" in names
    assert "order-secrets" in names
    assert "order-sa" in names


def test_discovery_safely_ignores_irrelevant_files(k8s_input_dir: Path):
    """Verify non-k8s files (shell scripts, notes) are ignored."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    source_files = {r.source_file for r in resources}

    assert not any("deploy.sh" in f for f in source_files)
    assert not any("notes.txt" in f for f in source_files)


def test_discovery_nonexistent_and_empty_directory(tmp_path: Path):
    """Verify appropriate error handling for missing and empty directories."""
    with pytest.raises(FileNotFoundError):
        ManifestDetector.discover_directory(tmp_path / "nonexistent")

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    resources = ManifestDetector.discover_directory(empty_dir)
    assert len(resources) == 0


def test_workspace_inspection(k8s_input_dir: Path):
    """Verify workspace inspection summarizes k8s resources and other technologies."""
    info = ManifestDetector.inspect_workspace(k8s_input_dir)

    assert info["k8s_resources_count"] >= 5
    assert "Deployment" in info["k8s_by_kind"]
    assert "Service" in info["k8s_by_kind"]
    assert "HorizontalPodAutoscaler" in info["k8s_by_kind"]


# ============================================================================
# 2. RELATIONSHIP & DEPENDENCY TESTS
# ============================================================================


def test_relationship_detection_hpa_and_workload(k8s_input_dir: Path):
    """Verify HPA -> Deployment relationship resolution."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    relationships = RelationshipAnalyzer.analyze(resources)

    hpa_rels = [r for r in relationships if r.rel_type == RelationshipType.HPA_TARGET]
    assert len(hpa_rels) == 1
    rel = hpa_rels[0]
    assert rel.source_name == "order-api-hpa"
    assert rel.target_name == "order-api"
    assert rel.status == RelationshipStatus.REFERENCED_AND_PRESENT


def test_relationship_detection_configmap_secret_sa(k8s_input_dir: Path):
    """Verify Deployment dependencies (ConfigMap, Secret, ServiceAccount) are linked."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    relationships = RelationshipAnalyzer.analyze(resources)

    # ConfigMap
    cm_rels = [r for r in relationships if r.rel_type == RelationshipType.ENV_CONFIGMAP]
    assert any(r.target_name == "order-config" and r.status == RelationshipStatus.REFERENCED_AND_PRESENT for r in cm_rels)

    # Secret
    sec_rels = [r for r in relationships if r.rel_type == RelationshipType.ENV_SECRET]
    assert any(r.target_name == "order-secrets" and r.status == RelationshipStatus.REFERENCED_AND_PRESENT for r in sec_rels)

    # ServiceAccount
    sa_rels = [r for r in relationships if r.rel_type == RelationshipType.SERVICE_ACCOUNT]
    assert any(r.target_name == "order-sa" and r.status == RelationshipStatus.REFERENCED_AND_PRESENT for r in sa_rels)


def test_relationship_detection_missing_reference(tmp_path: Path):
    """Verify REFERENCED_BUT_MISSING status when target resource is omitted."""
    dep_file = tmp_path / "dep.yaml"
    dep_file.write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: standalone-app
spec:
  template:
    spec:
      serviceAccountName: non-existent-sa
      containers:
        - name: app
          image: nginx
          envFrom:
            - configMapRef:
                name: missing-config
""",
        encoding="utf-8",
    )

    resources = ManifestDetector.discover_directory(tmp_path)
    relationships = RelationshipAnalyzer.analyze(resources)

    missing_cm = [r for r in relationships if r.target_name == "missing-config"]
    assert len(missing_cm) == 1
    assert missing_cm[0].status == RelationshipStatus.REFERENCED_BUT_MISSING

    missing_sa = [r for r in relationships if r.target_name == "non-existent-sa"]
    assert len(missing_sa) == 1
    assert missing_sa[0].status == RelationshipStatus.REFERENCED_BUT_MISSING


# ============================================================================
# 3. EXAMPLE INGESTION SYSTEM TESTS
# ============================================================================


def test_example_ingestion_and_registry(company_reference_chart: Path, tmp_path: Path):
    """Verify adding, listing, inspecting, and removing reference examples."""
    storage_dir = tmp_path / "examples_store"
    registry = ExampleRegistry(storage_dir=storage_dir)

    # 1. Add example
    pattern = registry.add_example(company_reference_chart, name="corp-std")
    assert pattern.name == "corp-std"
    assert pattern.chart_name == "corporate-standard"
    assert pattern.helper_prefix == "corp-standard"
    assert pattern.has_hpa is True
    assert pattern.has_ingress is True
    assert "deployment.yaml" in pattern.templates_found

    # 2. List examples
    listed = registry.list_examples()
    assert len(listed) == 1
    assert listed[0]["name"] == "corp-std"
    assert listed[0]["has_hpa"] is True

    # 3. Get example
    retrieved = registry.get_example("corp-std")
    assert retrieved.name == "corp-std"
    assert retrieved.helper_prefix == "corp-standard"

    # 4. Remove example
    removed = registry.remove_example("corp-std")
    assert removed is True
    assert len(registry.list_examples()) == 0


def test_example_ingestion_missing_chart_yaml(tmp_path: Path):
    """Verify ValueError when attempting to ingest a directory without Chart.yaml."""
    invalid_dir = tmp_path / "invalid_chart"
    invalid_dir.mkdir()
    (invalid_dir / "values.yaml").write_text("foo: bar\n", encoding="utf-8")

    registry = ExampleRegistry(storage_dir=tmp_path / "store")
    with pytest.raises(ValueError, match="No Chart.yaml found"):
        registry.add_example(invalid_dir)


# ============================================================================
# 4. REFERENCE-AWARE GENERATION TESTS
# ============================================================================


def test_generation_preserves_input_resources_and_ignores_extra_reference_resources(
    k8s_input_dir: Path,
    company_reference_chart: Path,
    tmp_path: Path,
):
    """Crucial requirement: Input determines WHAT is generated, reference determines HOW.

    Reference has Ingress and ConfigMap, but if input has no Ingress, Ingress MUST NOT be generated.
    """
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    # Notice: k8s_input_dir has NO Ingress manifest!
    assert not any(r.kind.lower() == "ingress" for r in resources)

    pattern = ExampleRegistry.analyze_chart(company_reference_chart)
    # Reference DOES have Ingress
    assert pattern.has_ingress is True

    output_dir = tmp_path / "generated-helm-chart"
    result = HelmGenerator.generate(
        resources=resources,
        target_dir=output_dir,
        chart_name="order-service",
        reference=pattern,
    )

    templates_dir = Path(result.target_dir) / "templates"
    assert (templates_dir / "deployment.yaml").is_file()
    assert (templates_dir / "service.yaml").is_file()
    assert (templates_dir / "hpa.yaml").is_file()
    assert (templates_dir / "_helpers.tpl").is_file()

    # INGRESS MUST NOT BE GENERATED because it was absent from input!
    assert not (templates_dir / "ingress.yaml").exists()


def test_generation_adopts_reference_conventions(
    k8s_input_dir: Path,
    company_reference_chart: Path,
    tmp_path: Path,
):
    """Verify helper prefix and label conventions from reference are adopted."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    pattern = ExampleRegistry.analyze_chart(company_reference_chart)

    output_dir = tmp_path / "out-corp"
    result = HelmGenerator.generate(
        resources=resources,
        target_dir=output_dir,
        chart_name="order-service",
        reference=pattern,
    )

    chart_path = Path(result.target_dir)
    helpers_content = (chart_path / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    assert 'define "corp-standard.fullname"' in helpers_content

    dep_content = (chart_path / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert 'include "corp-standard.fullname"' in dep_content
    assert 'include "corp-standard.labels"' in dep_content


def test_hpa_first_class_generation(k8s_input_dir: Path, tmp_path: Path):
    """Verify HPA generates templates/hpa.yaml and configures values.yaml autoscaling."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    output_dir = tmp_path / "hpa-test"
    result = HelmGenerator.generate(resources=resources, target_dir=output_dir, chart_name="my-app")

    chart_path = Path(result.target_dir)
    hpa_path = chart_path / "templates" / "hpa.yaml"
    assert hpa_path.is_file()
    hpa_content = hpa_path.read_text(encoding="utf-8")
    assert "apiVersion: autoscaling/v2" in hpa_content
    assert ".Values.autoscaling.enabled" in hpa_content

    values_path = chart_path / "values.yaml"
    values_data = yaml.safe_load(values_path.read_text(encoding="utf-8"))
    assert "autoscaling" in values_data
    assert values_data["autoscaling"]["enabled"] is True
    assert values_data["autoscaling"]["minReplicas"] == 2
    assert values_data["autoscaling"]["maxReplicas"] == 10
    assert values_data["autoscaling"]["targetCPUUtilizationPercentage"] == 75

    # Deployment should gate replicaCount with autoscaling.enabled
    dep_content = (chart_path / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert "if not .Values.autoscaling.enabled" in dep_content


def test_hpa_omitted_when_absent_from_input(tmp_path: Path):
    """Verify HPA is NOT generated when absent from input Kubernetes manifests."""
    k8s_simple = tmp_path / "k8s_simple"
    k8s_simple.mkdir()
    (k8s_simple / "deployment.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: nginx
          image: nginx:1.25
""",
        encoding="utf-8",
    )

    resources = ManifestDetector.discover_directory(k8s_simple)
    output_dir = tmp_path / "no-hpa-out"
    result = HelmGenerator.generate(resources=resources, target_dir=output_dir, chart_name="web")

    chart_path = Path(result.target_dir)
    assert not (chart_path / "templates" / "hpa.yaml").exists()

    values_data = yaml.safe_load((chart_path / "values.yaml").read_text(encoding="utf-8"))
    assert "autoscaling" not in values_data


# ============================================================================
# 5. SAFETY & IMMUTABILITY TESTS
# ============================================================================


def test_safety_input_and_reference_directories_remain_unmodified(
    k8s_input_dir: Path,
    company_reference_chart: Path,
    tmp_path: Path,
):
    """Verify input and reference directories are never modified during migration."""
    input_hashes_before = hash_directory(k8s_input_dir)
    ref_hashes_before = hash_directory(company_reference_chart)

    resources = ManifestDetector.discover_directory(k8s_input_dir)
    pattern = ExampleRegistry.analyze_chart(company_reference_chart)

    output_dir = tmp_path / "isolated-output"
    HelmGenerator.generate(
        resources=resources,
        target_dir=output_dir,
        chart_name="order-service",
        reference=pattern,
    )

    input_hashes_after = hash_directory(k8s_input_dir)
    ref_hashes_after = hash_directory(company_reference_chart)

    assert input_hashes_before == input_hashes_after, "Input directory was modified!"
    assert ref_hashes_before == ref_hashes_after, "Reference directory was modified!"


def test_migration_dry_run_writes_no_files(k8s_input_dir: Path, tmp_path: Path):
    """Verify --dry-run produces a complete plan without writing any files to disk."""
    resources = ManifestDetector.discover_directory(k8s_input_dir)
    output_dir = tmp_path / "dry-run-target"

    result = HelmGenerator.generate(
        resources=resources,
        target_dir=output_dir,
        chart_name="dry-chart",
        dry_run=True,
    )

    assert result.status == "dry_run"
    assert len(result.plan.planned_items) > 0
    assert not output_dir.exists()


# ============================================================================
# 6. VALIDATION ENGINE TESTS
# ============================================================================


def test_validation_engine_runs_without_crash(tmp_path: Path):
    """Verify MigrationValidator runs available tools and internal rule evaluations."""
    chart_dir = tmp_path / "val_chart"
    templates_dir = chart_dir / "templates"
    templates_dir.mkdir(parents=True)
    (chart_dir / "Chart.yaml").write_text("apiVersion: v2\nname: test\nversion: 0.1.0\n", encoding="utf-8")
    (templates_dir / "test.yaml").write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test-cm\n", encoding="utf-8")

    res = MigrationValidator.validate_chart(chart_dir)
    assert "executions" in res
    assert "diagnostics" in res
    assert len(res["executions"]) > 0


# ============================================================================
# 7. CLI COMMAND INTEGRATION TESTS
# ============================================================================


def test_cli_migrate_with_reference(k8s_input_dir: Path, company_reference_chart: Path, tmp_path: Path):
    """Verify CLI migrate command end-to-end with --reference."""
    runner = CliRunner()
    output_dir = tmp_path / "cli-migrated"

    result = runner.invoke(
        main,
        [
            "migrate",
            str(k8s_input_dir),
            "--to",
            "helm",
            "--reference",
            str(company_reference_chart),
            "--output",
            str(output_dir),
            "--name",
            "my-cli-app",
        ],
    )

    assert result.exit_code == 0
    assert "Migration Completed Successfully" in result.output
    assert (output_dir / "Chart.yaml").is_file()
    assert (output_dir / "values.yaml").is_file()
    assert (output_dir / "templates" / "deployment.yaml").is_file()
    assert (output_dir / "templates" / "hpa.yaml").is_file()


def test_cli_migrate_to_helm_first_argument_order(k8s_input_dir: Path, tmp_path: Path):
    """Verify both 'migrate ./k8s --to helm' and 'migrate --to helm ./k8s' work."""
    runner = CliRunner()
    output_dir = tmp_path / "cli-order-test"

    result = runner.invoke(
        main,
        [
            "migrate",
            "--to",
            "helm",
            str(k8s_input_dir),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "Chart.yaml").is_file()


def test_cli_migrate_dry_run_and_json(k8s_input_dir: Path, tmp_path: Path):
    """Verify CLI migrate with --dry-run --json outputs valid JSON plan."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "migrate",
            str(k8s_input_dir),
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "dry_run"
    assert "plan" in data
    assert len(data["plan"]["planned_items"]) >= 5


def test_cli_examples_commands_workflow(company_reference_chart: Path):
    """Verify devworkbench examples add, list, inspect, remove CLI workflow."""
    runner = CliRunner()

    # 1. examples add
    add_res = runner.invoke(main, ["examples", "add", str(company_reference_chart), "--name", "e2e-example"])
    assert add_res.exit_code == 0
    assert "Successfully ingested reference example" in add_res.output

    # 2. examples list
    list_res = runner.invoke(main, ["examples", "list"])
    assert list_res.exit_code == 0
    assert "e2e-example" in list_res.output

    # 3. examples inspect
    inspect_res = runner.invoke(main, ["examples", "inspect", "e2e-example"])
    assert inspect_res.exit_code == 0
    assert "corporate-standard" in inspect_res.output

    # 4. examples remove
    rem_res = runner.invoke(main, ["examples", "remove", "e2e-example"])
    assert rem_res.exit_code == 0
    assert "Removed reference example" in rem_res.output


def test_cli_helm_inspect(company_reference_chart: Path):
    """Verify devworkbench helm inspect CLI command."""
    runner = CliRunner()
    res = runner.invoke(main, ["helm", "inspect", str(company_reference_chart)])
    assert res.exit_code == 0
    assert "corporate-standard" in res.output
    assert "corp-standard" in res.output
