"""Helm chart reference ingestion, inspection, and local pattern storage."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

from devworkbench.migration.models import ReferencePattern

DEFAULT_EXAMPLES_DIR = Path.home() / ".devworkbench" / "examples"


class ExampleRegistry:
    """Manages local ingestion, inspection, and retrieval of reference Helm chart patterns."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or DEFAULT_EXAMPLES_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def add_example(self, chart_dir: Path, name: str | None = None) -> ReferencePattern:
        """Analyze a Helm chart directory, extract conventions, and save as a named reference pattern."""
        pattern = self.analyze_chart(chart_dir, reference_name=name)
        file_path = self.storage_dir / f"{pattern.name}.json"
        file_path.write_text(json.dumps(pattern.to_dict(), indent=2), encoding="utf-8")
        return pattern

    def list_examples(self) -> list[dict[str, Any]]:
        """List all locally stored reference chart examples."""
        examples: list[dict[str, Any]] = []
        if not self.storage_dir.exists():
            return examples

        for p in sorted(self.storage_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                examples.append(
                    {
                        "name": data.get("name", p.stem),
                        "chart_name": data.get("chart_name", "unknown"),
                        "chart_version": data.get("chart_version", "0.1.0"),
                        "templates_count": len(data.get("templates_found", [])),
                        "has_hpa": data.get("has_hpa", False),
                        "has_ingress": data.get("has_ingress", False),
                        "helper_prefix": data.get("helper_prefix", ""),
                    }
                )
            except Exception:
                continue
        return examples

    def get_example(self, name: str) -> ReferencePattern:
        """Retrieve a stored reference pattern by name."""
        file_path = self.storage_dir / f"{name}.json"
        if not file_path.is_file():
            raise FileNotFoundError(f"Reference example '{name}' not found.")
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return ReferencePattern(
            name=data["name"],
            chart_name=data.get("chart_name", name),
            chart_version=data.get("chart_version", "0.1.0"),
            app_version=data.get("app_version", "1.0.0"),
            helper_prefix=data.get("helper_prefix", ""),
            label_scheme=data.get("label_scheme", {}),
            values_hierarchy=data.get("values_hierarchy", {}),
            templates_found=data.get("templates_found", []),
            has_hpa=data.get("has_hpa", False),
            has_ingress=data.get("has_ingress", False),
            source_dir=data.get("source_dir"),
        )

    def remove_example(self, name: str) -> bool:
        """Remove a stored reference pattern by name."""
        file_path = self.storage_dir / f"{name}.json"
        if file_path.is_file():
            file_path.unlink()
            return True
        return False

    @classmethod
    def analyze_chart(cls, chart_dir: Path, reference_name: str | None = None) -> ReferencePattern:
        """Deeply analyze a Helm chart directory and extract metadata, conventions, and template patterns."""
        if not chart_dir.exists():
            raise FileNotFoundError(f"Chart directory does not exist: {chart_dir}")
        if not chart_dir.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {chart_dir}")

        chart_yaml_path = chart_dir / "Chart.yaml"
        if not chart_yaml_path.is_file():
            chart_yaml_path = chart_dir / "Chart.yml"
        if not chart_yaml_path.is_file():
            raise ValueError(f"No Chart.yaml found in reference directory: {chart_dir}")

        chart_metadata: dict[str, Any] = {}
        try:
            chart_metadata = yaml.safe_load(chart_yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            raise ValueError(f"Malformed Chart.yaml in reference directory: {e}") from e

        chart_name = chart_metadata.get("name", chart_dir.name)
        chart_version = str(chart_metadata.get("version", "0.1.0"))
        app_version = str(chart_metadata.get("appVersion", "1.0.0"))
        ref_name = reference_name or chart_name

        # 1. Read values.yaml
        values_data: dict[str, Any] = {}
        values_path = chart_dir / "values.yaml"
        if values_path.is_file():
            try:
                values_data = yaml.safe_load(values_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        # 2. Inspect templates
        templates_dir = chart_dir / "templates"
        templates_found: list[str] = []
        helper_prefix = ""
        label_scheme: dict[str, str] = {}
        has_hpa = False
        has_ingress = False
        hpa_pattern: dict[str, Any] | None = None
        service_pattern: dict[str, Any] | None = None
        deployment_pattern: dict[str, Any] | None = None

        if templates_dir.is_dir():
            for f in sorted(templates_dir.glob("*.yaml")) + sorted(templates_dir.glob("*.yml")):
                templates_found.append(f.name)
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    # Check kind
                    if "kind: HorizontalPodAutoscaler" in content or "kind: 'HorizontalPodAutoscaler'" in content:
                        has_hpa = True
                        hpa_pattern = {"template_file": f.name}
                    if "kind: Ingress" in content or "kind: 'Ingress'" in content:
                        has_ingress = True
                    if "kind: Service" in content:
                        service_pattern = {"template_file": f.name}
                    if "kind: Deployment" in content:
                        deployment_pattern = {"template_file": f.name}

                    # Detect labels used
                    for match in re.finditer(r"([a-zA-Z0-9\.\-_/]+):\s*(\{\{.*?\}\})", content):
                        k, v = match.groups()
                        if "name" in k or "instance" in k or "managed-by" in k or "chart" in k:
                            label_scheme[k] = v
                except Exception:
                    pass

            # Inspect _helpers.tpl for helper naming conventions
            helpers_path = templates_dir / "_helpers.tpl"
            if helpers_path.is_file():
                try:
                    h_content = helpers_path.read_text(encoding="utf-8", errors="replace")
                    # Match {{- define "<prefix>.name"
                    name_match = re.search(r'define\s+"([^"]+)\.name"', h_content)
                    if name_match:
                        helper_prefix = name_match.group(1)
                    else:
                        fn_match = re.search(r'define\s+"([^"]+)\.fullname"', h_content)
                        if fn_match:
                            helper_prefix = fn_match.group(1)
                except Exception:
                    pass

        if not helper_prefix:
            helper_prefix = chart_name

        # Check values for HPA
        if isinstance(values_data.get("autoscaling"), dict):
            has_hpa = True
            if hpa_pattern is None:
                hpa_pattern = {}
            hpa_pattern["values"] = values_data["autoscaling"]

        if isinstance(values_data.get("ingress"), dict):
            has_ingress = True

        return ReferencePattern(
            name=ref_name,
            chart_name=chart_name,
            chart_version=chart_version,
            app_version=app_version,
            helper_prefix=helper_prefix,
            label_scheme=label_scheme,
            values_hierarchy=values_data,
            templates_found=templates_found,
            has_hpa=has_hpa,
            hpa_pattern=hpa_pattern,
            has_ingress=has_ingress,
            service_pattern=service_pattern,
            deployment_pattern=deployment_pattern,
            source_dir=str(chart_dir),
        )
