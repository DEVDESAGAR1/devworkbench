"""Data models for reference-aware Kubernetes to Helm migration."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelationshipType(str, Enum):
    """Classification of references between Kubernetes resources."""

    HPA_TARGET = "HPA_TARGET"
    INGRESS_BACKEND = "INGRESS_BACKEND"
    ENV_CONFIGMAP = "ENV_CONFIGMAP"
    ENV_SECRET = "ENV_SECRET"
    VOLUME_CONFIGMAP = "VOLUME_CONFIGMAP"
    VOLUME_SECRET = "VOLUME_SECRET"
    VOLUME_PVC = "VOLUME_PVC"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    SERVICE_SELECTOR = "SERVICE_SELECTOR"


class RelationshipStatus(str, Enum):
    """Presence status of target referenced resources."""

    PRESENT = "PRESENT"
    REFERENCED_AND_PRESENT = "REFERENCED_AND_PRESENT"
    REFERENCED_BUT_MISSING = "REFERENCED_BUT_MISSING"
    NOT_REFERENCED = "NOT_REFERENCED"


@dataclass
class DiscoveredResource:
    """A Kubernetes resource discovered in an input directory."""

    api_version: str
    kind: str
    name: str
    namespace: str | None
    source_file: str
    source_doc_index: int
    raw_doc: dict[str, Any]
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)

    @property
    def identifier(self) -> str:
        return f"{self.kind}/{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_version": self.api_version,
            "kind": self.kind,
            "name": self.name,
            "namespace": self.namespace,
            "source_file": self.source_file,
            "source_doc_index": self.source_doc_index,
            "labels": self.labels,
            "annotations": self.annotations,
        }


@dataclass
class ResourceRelationship:
    """A detected relationship between two resources."""

    source_kind: str
    source_name: str
    target_kind: str
    target_name: str
    rel_type: RelationshipType
    status: RelationshipStatus
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": f"{self.source_kind}/{self.source_name}",
            "target": f"{self.target_kind}/{self.target_name}",
            "rel_type": self.rel_type.value,
            "status": self.status.value,
            "details": self.details,
        }


@dataclass
class ReferencePattern:
    """Conventions and reusable patterns extracted from an existing Helm chart."""

    name: str
    chart_name: str
    chart_version: str = "0.1.0"
    app_version: str = "1.0.0"
    helper_prefix: str = ""
    label_scheme: dict[str, str] = field(default_factory=dict)
    values_hierarchy: dict[str, Any] = field(default_factory=dict)
    templates_found: list[str] = field(default_factory=list)
    has_hpa: bool = False
    hpa_pattern: dict[str, Any] | None = None
    has_ingress: bool = False
    ingress_pattern: dict[str, Any] | None = None
    service_pattern: dict[str, Any] | None = None
    deployment_pattern: dict[str, Any] | None = None
    source_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "chart_name": self.chart_name,
            "chart_version": self.chart_version,
            "app_version": self.app_version,
            "helper_prefix": self.helper_prefix,
            "label_scheme": self.label_scheme,
            "templates_found": self.templates_found,
            "has_hpa": self.has_hpa,
            "has_ingress": self.has_ingress,
            "source_dir": self.source_dir,
            "values_hierarchy": self.values_hierarchy,
        }


@dataclass
class MigrationPlanItem:
    """An individual resource planned for template generation."""

    source_resource: str
    kind: str
    target_file: str
    pattern_applied: str | None
    provider: str  # e.g., "reference-pattern", "DEVWORKBENCH", "NATIVE"
    reason: str

    priority: str = "DEVWORKBENCH"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_resource": self.source_resource,
            "kind": self.kind,
            "target_file": self.target_file,
            "pattern_applied": self.pattern_applied,
            "provider": self.provider,
            "priority": self.priority,
            "reason": self.reason,
        }


@dataclass
class MigrationPlan:
    """Plan describing the end-to-end migration execution."""

    input_directory: str
    target_chart_name: str
    target_directory: str
    reference_name: str | None
    discovered_resources: list[DiscoveredResource] = field(default_factory=list)
    relationships: list[ResourceRelationship] = field(default_factory=list)
    planned_items: list[MigrationPlanItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_directory": self.input_directory,
            "target_chart_name": self.target_chart_name,
            "target_directory": self.target_directory,
            "reference_name": self.reference_name,
            "resources_count": len(self.discovered_resources),
            "discovered_resources": [r.to_dict() for r in self.discovered_resources],
            "relationships": [rel.to_dict() for rel in self.relationships],
            "planned_items": [item.to_dict() for item in self.planned_items],
        }


@dataclass
class MigrationResult:
    """Outcome of a migration execution."""

    target_dir: str
    chart_name: str
    plan: MigrationPlan
    created_files: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    kept_files: list[str] = field(default_factory=list)
    validation_executions: list[Any] = field(default_factory=list)
    validation_diagnostics: list[Any] = field(default_factory=list)
    duration_ms: float = 0.0
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_dir": self.target_dir,
            "chart_name": self.chart_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "created_files": self.created_files,
            "updated_files": self.updated_files,
            "kept_files": self.kept_files,
            "plan": self.plan.to_dict(),
            "validation_executions": [e.to_dict() for e in self.validation_executions],
            "validation_diagnostics": [d.to_dict() for d in self.validation_diagnostics],
        }
