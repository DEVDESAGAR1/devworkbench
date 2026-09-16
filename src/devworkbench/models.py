"""Domain models and data structures for DevWorkBench."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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


TECHNOLOGY_CATEGORIES: Dict[Technology, FileCategory] = {
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
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    rule: Optional[str] = None
    category: DiagnosticCategory = DiagnosticCategory.LINT
    fix_available: bool = False
    fix_kind: FixKind = FixKind.NONE
    fix_source: Optional[str] = None
    fix_safety: FixSafety = FixSafety.UNSAFE
    fix_description: Optional[str] = None
    details: Optional[str] = None
    provider: Optional[str] = None
    provider_priority: Optional[int] = None
    provider_type: Optional[str] = None  # "native", "opensource", "devworkbench", "manual"
    rule_origin: Optional[str] = None  # "External engine", "DevWorkBench rule engine"
    documentation_url: Optional[str] = None
    help_url: Optional[str] = None
    contributing_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
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
    documentation_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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
    related_failures: List[str] = field(default_factory=list)
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
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
    technology_chain: List[str]
    root_cause_candidate: Optional[RootCauseCandidate]
    confidence: float  # 0.0 to 1.0
    explanation: str
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
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
    diagnostics: List[Diagnostic] = field(default_factory=list)
    root_causes: List[RootCauseCandidate] = field(default_factory=list)
    correlations: List[Correlation] = field(default_factory=list)
    duration_ms: float = 0.0
    modified_files: int = 0  # Invariant: 0

    def to_dict(self) -> Dict[str, Any]:
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
    details: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
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
    chart_yaml: Optional[str] = None
    values_files: List[str] = field(default_factory=list)
    template_files: List[str] = field(default_factory=list)
    helper_files: List[str] = field(default_factory=list)
    subchart_files: List[str] = field(default_factory=list)
    other_files: List[str] = field(default_factory=list)

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

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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
        }


@dataclass
class ScanError:
    """Represents an error encountered on a file during scanning."""

    path: str
    relative_path: str
    error_message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "error_message": self.error_message,
        }


@dataclass
class ScanResult:
    """Complete structured output of a workspace scan and analysis."""

    target_path: str
    detections: List[FileDetection] = field(default_factory=list)
    helm_charts: List[HelmChart] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    correlations: List[Correlation] = field(default_factory=list)
    tool_warnings: List[ToolWarning] = field(default_factory=list)
    unknown_files: List[FileDetection] = field(default_factory=list)
    errors: List[ScanError] = field(default_factory=list)
    summary: ScanSummary = field(default_factory=ScanSummary)

    def to_dict(self) -> Dict[str, Any]:
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
        }


@dataclass
class FixCandidate:
    """An individual actionable fix proposal for a specific diagnostic."""

    path: str
    rule: Optional[str]
    message: str
    source: str
    fix_kind: FixKind
    fix_safety: FixSafety
    description: str
    line: Optional[int] = None
    column: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
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
    candidates: List[FixCandidate] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
            "candidates": [c.to_dict() for c in self.candidates],
        }


@dataclass
class FixPlan:
    """The generated plan of proposed fixes before user confirmation."""

    target_paths: List[str]
    safe_candidates: List[FixCandidate] = field(default_factory=list)
    manual_candidates: List[FixCandidate] = field(default_factory=list)
    conflicts: List[FixConflict] = field(default_factory=list)
    files_to_modify: List[str] = field(default_factory=list)
    file_hashes_before: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
    rule: Optional[str]
    source: str
    status: str  # "applied", "skipped", "failed"
    message: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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

    target_paths: List[str]
    plan: FixPlan
    summary: FixSummary
    results: List[FixResultItem] = field(default_factory=list)
    remaining_diagnostics: List[Diagnostic] = field(default_factory=list)
    resolved_diagnostics: List[Diagnostic] = field(default_factory=list)
    engine_states: Dict[str, str] = field(default_factory=dict)
    confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
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

