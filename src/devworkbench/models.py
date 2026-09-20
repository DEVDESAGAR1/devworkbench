"""Domain models and data structures for DevWorkBench."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Technology(str, Enum):
    """Supported DevOps and Developer technologies."""

    # DevOps Technologies
    JENKINS = "Jenkins"
    KUBERNETES = "Kubernetes"
    OPENSHIFT = "OpenShift"
    HELM = "Helm"
    TERRAFORM = "Terraform"
    ANSIBLE = "Ansible"
    DOCKERFILE = "Dockerfile"
    DOCKER_COMPOSE = "Docker Compose"
    GITHUB_ACTIONS = "GitHub Actions"
    GITLAB_CI = "GitLab CI"
    SHELL = "Shell"
    AWS = "AWS"
    AZURE = "Azure"
    GCP = "GCP"

    # Developer File Technologies
    PYTHON = "Python"
    JSON = "JSON"
    YAML = "YAML"
    XML = "XML"
    SQL = "SQL"
    JAVASCRIPT = "JavaScript"
    TYPESCRIPT = "TypeScript"
    JAVA = "Java"

    # Build / Runtime Log Technology
    BUILD_LOG = "Build Log"

    # Fallback
    UNKNOWN = "Unknown"


class FileCategory(str, Enum):
    """Categorization of detected files."""

    DEVOPS = "DevOps"
    DEVELOPER = "Developer"
    CONFIG = "Config"
    BUILD_LOG = "BuildLog"
    UNKNOWN = "Unknown"


TECHNOLOGY_CATEGORIES: dict[Technology, FileCategory] = {
    Technology.JENKINS: FileCategory.DEVOPS,
    Technology.KUBERNETES: FileCategory.DEVOPS,
    Technology.OPENSHIFT: FileCategory.DEVOPS,
    Technology.HELM: FileCategory.DEVOPS,
    Technology.TERRAFORM: FileCategory.DEVOPS,
    Technology.ANSIBLE: FileCategory.DEVOPS,
    Technology.DOCKERFILE: FileCategory.DEVOPS,
    Technology.DOCKER_COMPOSE: FileCategory.DEVOPS,
    Technology.GITHUB_ACTIONS: FileCategory.DEVOPS,
    Technology.GITLAB_CI: FileCategory.DEVOPS,
    Technology.SHELL: FileCategory.DEVOPS,
    Technology.AWS: FileCategory.DEVOPS,
    Technology.AZURE: FileCategory.DEVOPS,
    Technology.GCP: FileCategory.DEVOPS,
    Technology.PYTHON: FileCategory.DEVELOPER,
    Technology.JSON: FileCategory.CONFIG,
    Technology.YAML: FileCategory.CONFIG,
    Technology.XML: FileCategory.CONFIG,
    Technology.SQL: FileCategory.DEVELOPER,
    Technology.JAVASCRIPT: FileCategory.DEVELOPER,
    Technology.TYPESCRIPT: FileCategory.DEVELOPER,
    Technology.JAVA: FileCategory.DEVELOPER,
    Technology.BUILD_LOG: FileCategory.BUILD_LOG,
    Technology.UNKNOWN: FileCategory.UNKNOWN,
}


class DiagnosticSeverity(str, Enum):
    """Severity levels for normalized diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


class DiagnosticCategory(str, Enum):
    """Category of diagnostic problem."""

    SYNTAX = "syntax"
    LINT = "lint"
    FORMAT = "format"
    SCHEMA = "schema"
    SECURITY = "security"
    BEST_PRACTICE = "best-practice"
    TYPE_CHECK = "type_check"
    RUNTIME_ERROR = "runtime_error"


class FixKind(str, Enum):
    """Classification of fix mechanism."""

    NONE = "NONE"
    NATIVE_ENGINE = "NATIVE_ENGINE"
    DEVWORKBENCH_SAFE = "DEVWORKBENCH_SAFE"
    MANUAL = "MANUAL"


class FixSafety(str, Enum):
    """Safety rating of a proposed fix."""

    SAFE = "SAFE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSAFE = "UNSAFE"


class ToolState(str, Enum):
    """Detailed operational state of an analysis or fix engine."""

    AVAILABLE = "AVAILABLE"
    NOT_INSTALLED = "NOT_INSTALLED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    TIMEOUT = "TIMEOUT"
    OUTPUT_INVALID = "OUTPUT_INVALID"
    SKIPPED = "SKIPPED"
    ANALYZED = "ANALYZED"
    FIXED = "FIXED"
    FIX_FAILED = "FIX_FAILED"


@dataclass
class Diagnostic:
    """Normalized diagnostic result from any tool, rule, or analyzer."""

    path: str
    message: str
    source: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    rule: str | None = None
    category: DiagnosticCategory = DiagnosticCategory.LINT
    fix_available: bool = False
    fix_kind: FixKind = FixKind.NONE
    fix_source: str | None = None
    fix_safety: FixSafety = FixSafety.UNSAFE
    fix_description: str | None = None
    details: str | None = None
    provider: str | None = None
    provider_priority: int | None = None
    provider_type: str | None = None  # "native", "opensource", "devworkbench", "manual"
    rule_origin: str | None = None  # "External engine", "DevWorkBench rule engine"
    documentation_url: str | None = None
    help_url: str | None = None
    contributing_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "severity": self.severity.value,
            "rule": self.rule,
            "message": self.message,
            "source": self.source,
            "category": self.category.value,
            "fix_available": self.fix_available,
            "fix_kind": self.fix_kind.value if hasattr(self.fix_kind, "value") else str(self.fix_kind),
            "fix_source": self.fix_source,
            "fix_safety": self.fix_safety.value if hasattr(self.fix_safety, "value") else str(self.fix_safety),
            "fix_description": self.fix_description,
            "details": self.details,
            "provider": self.provider,
            "provider_priority": self.provider_priority,
            "provider_type": self.provider_type,
            "rule_origin": self.rule_origin,
            "documentation_url": self.documentation_url,
            "contributing_sources": self.contributing_sources,
        }


@dataclass
class ToolWarning:
    """Warning when an optional external tool/linter is unavailable."""

    technology: Technology
    tool_name: str
    install_hint: str
    documentation_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "technology": self.technology.value,
            "tool_name": self.tool_name,
            "install_hint": self.install_hint,
            "documentation_url": self.documentation_url,
        }


@dataclass
class RootCauseCandidate:
    """Represents an identified root cause from build logs or cross-tool analysis."""

    title: str
    source: str
    category: str
    confidence: str  # "Likely root cause" or "Possible root cause"
    description: str
    related_failures: list[str] = field(default_factory=list)
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "category": self.category,
            "confidence": self.confidence,
            "description": self.description,
            "related_failures": self.related_failures,
            "line_number": self.line_number,
        }


@dataclass
class Correlation:
    """Represents a deterministic correlation chain across DevOps technologies."""

    id: str
    technology_chain: list[str]
    root_cause_candidate: RootCauseCandidate | None
    confidence: float  # 0.0 to 1.0
    explanation: str
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "technology_chain": self.technology_chain,
            "root_cause_candidate": self.root_cause_candidate.to_dict() if self.root_cause_candidate else None,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass
class BuildLogReport:
    """Structured report generated from build log analysis."""

    source_path: str
    total_lines: int
    diagnostics: list[Diagnostic] = field(default_factory=list)
    root_causes: list[RootCauseCandidate] = field(default_factory=list)
    correlations: list[Correlation] = field(default_factory=list)
    duration_ms: float = 0.0
    modified_files: int = 0  # Invariant: 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "total_lines": self.total_lines,
            "root_causes": [rc.to_dict() for rc in self.root_causes],
            "correlations": [c.to_dict() for c in self.correlations],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "duration_ms": self.duration_ms,
            "modified_files": self.modified_files,
        }


@dataclass
class FileDetection:
    """Represents a successfully detected file."""

    path: str
    relative_path: str
    technology: Technology
    category: FileCategory
    confidence: float = 1.0
    details: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "technology": self.technology.value,
            "category": self.category.value,
            "confidence": self.confidence,
            "details": self.details,
            "metadata": self.metadata,
            "size_bytes": self.size_bytes,
        }


@dataclass
class HelmChart:
    """Represents a discovered Helm Chart project and its hierarchy."""

    name: str
    root_path: str
    relative_root: str
    chart_yaml: str | None = None
    values_files: list[str] = field(default_factory=list)
    template_files: list[str] = field(default_factory=list)
    helper_files: list[str] = field(default_factory=list)
    subchart_files: list[str] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        count = 1 if self.chart_yaml else 0
        return (
            count
            + len(self.values_files)
            + len(self.template_files)
            + len(self.helper_files)
            + len(self.subchart_files)
            + len(self.other_files)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root_path": self.root_path,
            "relative_root": self.relative_root,
            "chart_yaml": self.chart_yaml,
            "values_files": self.values_files,
            "template_files": self.template_files,
            "helper_files": self.helper_files,
            "subchart_files": self.subchart_files,
            "other_files": self.other_files,
            "total_files": self.total_files,
        }


@dataclass
class CommandExecution:
    """Structured record of an external or internal command execution."""

    technology: str
    capability: str
    provider_type: str  # "native", "opensource", "devworkbench", "manual"
    provider_name: str
    executable: str
    args: list[str]
    command: str
    cwd: str
    status: str  # "PASS", "FAIL", "UNAVAILABLE", "SKIPPED", "DEGRADED", "MANUAL_REVIEW"
    duration_ms: float = 0.0
    exit_code: int | None = None
    tool_version: str | None = None
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None
    fallback_provider: str | None = None
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "technology": self.technology,
            "capability": self.capability,
            "provider_type": self.provider_type,
            "provider_name": self.provider_name,
            "tool_version": self.tool_version,
            "executable": self.executable,
            "args": self.args,
            "command": self.command,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_message": self.error_message,
            "fallback_provider": self.fallback_provider,
            "unavailable_reason": self.unavailable_reason,
        }


class CheckCoverage(str, Enum):
    """Overall coverage rating of the executed checks."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"


@dataclass
class ScanSummary:
    """Aggregated metrics for a scan and analysis operation."""

    total_files_discovered: int = 0
    supported_files: int = 0
    unknown_files: int = 0
    error_files: int = 0
    helm_charts_count: int = 0
    analyzed_files: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    files_with_issues: int = 0
    tools_unavailable_count: int = 0
    root_causes_count: int = 0
    duration_ms: float = 0.0
    modified_files: int = 0  # Must always remain 0 during scan
    coverage: CheckCoverage = CheckCoverage.FULL
    checks_passed: int = 0
    checks_failed: int = 0
    checks_unavailable: int = 0
    checks_skipped: int = 0
    checks_degraded: int = 0
    manual_review_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files_discovered": self.total_files_discovered,
            "supported_files": self.supported_files,
            "unknown_files": self.unknown_files,
            "error_files": self.error_files,
            "helm_charts_count": self.helm_charts_count,
            "analyzed_files": self.analyzed_files,
            "errors_count": self.errors_count,
            "warnings_count": self.warnings_count,
            "files_with_issues": self.files_with_issues,
            "tools_unavailable_count": self.tools_unavailable_count,
            "root_causes_count": self.root_causes_count,
            "duration_ms": self.duration_ms,
            "modified_files": self.modified_files,
            "coverage": self.coverage.value if hasattr(self.coverage, "value") else str(self.coverage),
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "checks_unavailable": self.checks_unavailable,
            "checks_skipped": self.checks_skipped,
            "checks_degraded": self.checks_degraded,
            "manual_review_count": self.manual_review_count,
        }


@dataclass
class ScanError:
    """Represents an error encountered on a file during scanning."""

    path: str
    relative_path: str
    error_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "error_message": self.error_message,
        }


@dataclass
class ScanResult:
    """Complete structured output of a workspace scan and analysis."""

    target_path: str
    detections: list[FileDetection] = field(default_factory=list)
    helm_charts: list[HelmChart] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    correlations: list[Correlation] = field(default_factory=list)
    tool_warnings: list[ToolWarning] = field(default_factory=list)
    unknown_files: list[FileDetection] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)
    executions: list[CommandExecution] = field(default_factory=list)
    summary: ScanSummary = field(default_factory=ScanSummary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_path": self.target_path,
            "summary": self.summary.to_dict(),
            "helm_charts": [hc.to_dict() for hc in self.helm_charts],
            "detections": [d.to_dict() for d in self.detections],
            "diagnostics": [diag.to_dict() for diag in self.diagnostics],
            "correlations": [c.to_dict() for c in self.correlations],
            "tool_warnings": [tw.to_dict() for tw in self.tool_warnings],
            "unknown_files": [u.to_dict() for u in self.unknown_files],
            "errors": [e.to_dict() for e in self.errors],
            "executions": [e.to_dict() for e in self.executions],
        }


class ResourceAction(str, Enum):
    """Classification of resources during conversion/reconciliation."""

    KEEP = "KEEP"
    UPDATE = "UPDATE"
    CREATE = "CREATE"
    REVIEW = "REVIEW"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class ResourcePlanItem:
    """An individual resource planned for conversion into Helm."""

    kind: str
    name: str
    api_version: str
    action: ResourceAction
    target_file: str
    reason: str
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "api_version": self.api_version,
            "action": self.action.value,
            "target_file": self.target_file,
            "reason": self.reason,
            "details": self.details,
        }


@dataclass
class ConversionPlan:
    """Plan detailing how Kubernetes manifests will be converted into a Helm chart."""

    source_paths: list[str]
    target_chart_name: str
    target_dir: str
    existing_chart_detected: bool
    resource_items: list[ResourcePlanItem] = field(default_factory=list)
    engine_used: str = "internal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_paths": self.source_paths,
            "target_chart_name": self.target_chart_name,
            "target_dir": self.target_dir,
            "existing_chart_detected": self.existing_chart_detected,
            "engine_used": self.engine_used,
            "resource_items": [item.to_dict() for item in self.resource_items],
        }


@dataclass
class ConversionResult:
    """Result of converting Kubernetes manifests into a Helm chart."""

    target_dir: str
    chart_name: str
    plan: ConversionPlan
    created_files: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    kept_files: list[str] = field(default_factory=list)
    validation_diagnostics: list[Diagnostic] = field(default_factory=list)
    executions: list[CommandExecution] = field(default_factory=list)
    duration_ms: float = 0.0
    status: str = "success"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_dir": self.target_dir,
            "chart_name": self.chart_name,
            "status": self.status,
            "error": self.error,
            "plan": self.plan.to_dict(),
            "created_files": self.created_files,
            "updated_files": self.updated_files,
            "kept_files": self.kept_files,
            "validation_diagnostics": [d.to_dict() for d in self.validation_diagnostics],
            "executions": [e.to_dict() for e in self.executions],
            "duration_ms": self.duration_ms,
        }


@dataclass
class CleanupResult:
    """Result of cleaning a Kubernetes manifest."""

    source_path: str
    original_yaml: str
    cleaned_yaml: str
    fields_removed: list[str] = field(default_factory=list)
    diff: str = ""
    engine_used: str = "internal"
    execution: CommandExecution | None = None
    validation_passed: bool = True
    written: bool = False
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "original_yaml": self.original_yaml,
            "cleaned_yaml": self.cleaned_yaml,
            "fields_removed": self.fields_removed,
            "diff": self.diff,
            "engine_used": self.engine_used,
            "execution": self.execution.to_dict() if self.execution else None,
            "validation_passed": self.validation_passed,
            "written": self.written,
            "output_path": self.output_path,
        }


@dataclass
class FixCandidate:
    """An individual actionable fix proposal for a specific diagnostic."""

    path: str
    rule: str | None
    message: str
    source: str
    fix_kind: FixKind
    fix_safety: FixSafety
    description: str
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "rule": self.rule,
            "message": self.message,
            "source": self.source,
            "fix_kind": self.fix_kind.value if hasattr(self.fix_kind, "value") else str(self.fix_kind),
            "fix_safety": self.fix_safety.value if hasattr(self.fix_safety, "value") else str(self.fix_safety),
            "description": self.description,
        }


@dataclass
class FixConflict:
    """Represents an overlapping or conflicting fix scenario."""

    path: str
    reason: str
    candidates: list[FixCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
            "candidates": [c.to_dict() for c in self.candidates],
        }


@dataclass
class FixPlan:
    """The generated plan of proposed fixes before user confirmation."""

    target_paths: list[str]
    safe_candidates: list[FixCandidate] = field(default_factory=list)
    manual_candidates: list[FixCandidate] = field(default_factory=list)
    conflicts: list[FixConflict] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    file_hashes_before: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_paths": self.target_paths,
            "files_to_modify": self.files_to_modify,
            "safe_fixes_count": len(self.safe_candidates),
            "manual_fixes_count": len(self.manual_candidates),
            "conflicts_count": len(self.conflicts),
            "safe_candidates": [c.to_dict() for c in self.safe_candidates],
            "manual_candidates": [c.to_dict() for c in self.manual_candidates],
            "conflicts": [conf.to_dict() for conf in self.conflicts],
            "file_hashes_before": self.file_hashes_before,
        }


@dataclass
class FixResultItem:
    """Result of applying a fix on a file."""

    path: str
    rule: str | None
    source: str
    status: str  # "applied", "skipped", "failed"
    message: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rule": self.rule,
            "source": self.source,
            "status": self.status,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class FixSummary:
    """Summary metrics of fix execution and validation."""

    files_analyzed: int = 0
    fix_candidates: int = 0
    applied_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    resolved_count: int = 0
    remaining_count: int = 0
    files_modified: int = 0
    before_errors: int = 0
    before_warnings: int = 0
    after_errors: int = 0
    after_warnings: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_analyzed": self.files_analyzed,
            "fix_candidates": self.fix_candidates,
            "applied": self.applied_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
            "resolved": self.resolved_count,
            "remaining": self.remaining_count,
            "files_modified": self.files_modified,
            "before_errors": self.before_errors,
            "before_warnings": self.before_warnings,
            "after_errors": self.after_errors,
            "after_warnings": self.after_warnings,
            "duration_ms": self.duration_ms,
        }


@dataclass
class FixReport:
    """Comprehensive report detailing fix planning, execution, and validation."""

    target_paths: list[str]
    plan: FixPlan
    summary: FixSummary
    results: list[FixResultItem] = field(default_factory=list)
    remaining_diagnostics: list[Diagnostic] = field(default_factory=list)
    resolved_diagnostics: list[Diagnostic] = field(default_factory=list)
    engine_states: dict[str, str] = field(default_factory=dict)
    confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_paths": self.target_paths,
            "confirmed": self.confirmed,
            "summary": self.summary.to_dict(),
            "plan": self.plan.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "resolved_diagnostics": [d.to_dict() for d in self.resolved_diagnostics],
            "remaining_diagnostics": [d.to_dict() for d in self.remaining_diagnostics],
            "engine_states": self.engine_states,
        }

