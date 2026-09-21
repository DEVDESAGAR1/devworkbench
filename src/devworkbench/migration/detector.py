"""Discovery and parsing of Kubernetes manifests from directories and workspaces."""

import os
from pathlib import Path
from typing import Any

import yaml

from devworkbench.migration.models import DiscoveredResource

KNOWN_K8S_KINDS = {
    "deployment",
    "statefulset",
    "daemonset",
    "job",
    "cronjob",
    "service",
    "ingress",
    "horizontalpodautoscaler",
    "configmap",
    "secret",
    "persistentvolumeclaim",
    "serviceaccount",
    "role",
    "rolebinding",
    "clusterrole",
    "clusterrolebinding",
    "networkpolicy",
    "poddisruptionbudget",
}


class ManifestDetector:
    """Discovers and parses Kubernetes manifests across a workspace directory."""

    @classmethod
    def discover_directory(cls, input_dir: Path) -> list[DiscoveredResource]:
        """Recursively scan directory for all valid Kubernetes YAML manifests."""
        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
        if not input_dir.is_dir():
            raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

        resources: list[DiscoveredResource] = []

        # Recursively walk the directory, sort for deterministic order
        for root, dirs, files in os.walk(input_dir):
            # Sort directories and files for deterministic traversal
            dirs.sort()
            files.sort()
            for f in files:
                if f.endswith((".yaml", ".yml")):
                    file_path = Path(root) / f
                    parsed = cls._parse_file(file_path, base_dir=input_dir)
                    resources.extend(parsed)

        return resources

    @classmethod
    def _parse_file(cls, file_path: Path, base_dir: Path) -> list[DiscoveredResource]:
        """Parse all valid Kubernetes documents within a single YAML file."""
        discovered: list[DiscoveredResource] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        try:
            docs = list(yaml.safe_load_all(content))
        except Exception:
            # Skip unparseable files safely
            return []

        try:
            rel_path = file_path.relative_to(base_dir).as_posix()
        except ValueError:
            rel_path = file_path.as_posix()

        for idx, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            api_ver = doc.get("apiVersion")
            kind = doc.get("kind")
            metadata = doc.get("metadata")

            # Must have apiVersion, kind, and metadata name to be a valid k8s resource
            if not (api_ver and kind and isinstance(metadata, dict)):
                continue

            name = metadata.get("name")
            if not name or not isinstance(name, str):
                continue

            namespace = metadata.get("namespace")
            labels = metadata.get("labels", {})
            if not isinstance(labels, dict):
                labels = {}
            annotations = metadata.get("annotations", {})
            if not isinstance(annotations, dict):
                annotations = {}

            spec = doc.get("spec", {})
            if not isinstance(spec, dict):
                spec = {}

            discovered.append(
                DiscoveredResource(
                    api_version=str(api_ver),
                    kind=str(kind),
                    name=str(name),
                    namespace=str(namespace) if namespace else None,
                    source_file=rel_path,
                    source_doc_index=idx,
                    raw_doc=doc,
                    labels={str(k): str(v) for k, v in labels.items()},
                    annotations={str(k): str(v) for k, v in annotations.items()},
                    spec=spec,
                )
            )

        return discovered

    @classmethod
    def inspect_workspace(cls, workspace_dir: Path) -> dict[str, Any]:
        """Inspect the current workspace directory for migration candidates."""
        k8s_resources: list[DiscoveredResource] = []
        helm_charts: list[str] = []
        other_tech: set[str] = set()

        if not workspace_dir.is_dir():
            return {
                "workspace": str(workspace_dir),
                "k8s_resources_count": 0,
                "k8s_by_kind": {},
                "helm_charts": [],
                "other_technologies": [],
            }

        # Check for existing Helm charts (directories containing Chart.yaml)
        for root, dirs, files in os.walk(workspace_dir):
            dirs.sort()
            if "Chart.yaml" in files or "Chart.yml" in files:
                chart_path = Path(root)
                try:
                    rel = chart_path.relative_to(workspace_dir).as_posix()
                    helm_charts.append(rel or ".")
                except ValueError:
                    helm_charts.append(chart_path.as_posix())

            # Detect other technologies in current workspace
            for f in files:
                if f == "Dockerfile" or f.startswith("Dockerfile."):
                    other_tech.add("Dockerfile")
                elif f.endswith((".tf", ".tofu")):
                    other_tech.add("Terraform")
                elif f.startswith("Jenkinsfile"):
                    other_tech.add("Jenkins")
                elif f in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml"):
                    other_tech.add("Docker Compose")

        # Discover k8s manifests (excluding any helm templates directories to avoid confusion)
        for root, dirs, files in os.walk(workspace_dir):
            dirs.sort()
            # If current directory is inside a Helm chart, don't double count as raw k8s input
            if "templates" in Path(root).parts and any(
                (Path(root).parents[i] / "Chart.yaml").is_file() for i in range(len(Path(root).parents))
            ):
                continue

            for f in files:
                if f.endswith((".yaml", ".yml")):
                    file_p = Path(root) / f
                    parsed = cls._parse_file(file_p, base_dir=workspace_dir)
                    k8s_resources.extend(parsed)

        # Count by kind
        by_kind: dict[str, int] = {}
        for r in k8s_resources:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + 1

        return {
            "workspace": str(workspace_dir),
            "k8s_resources_count": len(k8s_resources),
            "k8s_by_kind": dict(sorted(by_kind.items())),
            "helm_charts": sorted(helm_charts),
            "other_technologies": sorted(list(other_tech)),
            "resources": k8s_resources,
        }
