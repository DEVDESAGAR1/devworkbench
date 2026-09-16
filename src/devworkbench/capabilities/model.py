"""Data models and enums for the Tool Selection Hierarchy, Capabilities, and Dependency Installation."""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional

from devworkbench.models import Technology


class ToolPriority(IntEnum):
    """Mandatory tool selection priority hierarchy."""

    NATIVE = 1        # Official / ecosystem tool (helm, terraform, ruff, shellcheck, etc.)
    OPENSOURCE = 2    # Established open-source tool / Python library (pyyaml, checkov, tflint, etc.)
    DEVWORKBENCH = 3  # DevWorkBench deterministic logic / custom rule engine
    MANUAL = 4        # Manual review required (no safe automated capability)


class CapabilityType(str, Enum):
    """Supported DevOps and Developer capabilities."""

    # Helm
    HELM_LINT = "helm_lint"
    HELM_RENDER = "helm_render"
    HELM_SCHEMA_VALIDATION = "helm_schema_validation"
    HELM_CONVERSION = "helm_conversion"

    # Terraform / OpenTofu
    TERRAFORM_FORMAT = "terraform_format"
    TERRAFORM_VALIDATE = "terraform_validate"
    TERRAFORM_LINT = "terraform_lint"
    TERRAFORM_SECURITY = "terraform_security"

    # Python
    PYTHON_SYNTAX = "python_syntax"
    PYTHON_LINT = "python_lint"
    PYTHON_FORMAT = "python_format"

    # YAML
    YAML_PARSING = "yaml_parsing"
    YAML_LINT = "yaml_lint"

    # Shell / Bash
    SHELL_LINT = "shell_lint"

    # Docker / Containers
    DOCKERFILE_LINT = "dockerfile_lint"

    # Kubernetes & OpenShift
    KUBERNETES_SCHEMA_VALIDATION = "kubernetes_schema_validation"
    KUBERNETES_LINT = "kubernetes_lint"
    KUBERNETES_TO_HELM = "kubernetes_to_helm"
    OPENSHIFT_VALIDATION = "openshift_validation"

    # Ansible & CI/CD
    ANSIBLE_LINT = "ansible_lint"
    GITHUB_ACTIONS_LINT = "github_actions_lint"
    GITLAB_CI_LINT = "gitlab_ci_lint"
    JENKINS_VALIDATION = "jenkins_validation"
    JENKINS_SECURITY = "jenkins_security"

    # Build Log Analysis
    BUILD_LOG_ANALYSIS = "build_log_analysis"


class InstallMethod(str, Enum):
    """Method used to install a tool or dependency."""

    PIP = "pip"
    SYSTEM_PACKAGE = "system_package"
    MANUAL = "manual"
    BUILTIN = "builtin"


class InstallationErrorKind(str, Enum):
    """Structured classification of installation and dependency failures."""

    ALREADY_INSTALLED = "ALREADY_INSTALLED"
    COMMAND_NOT_FOUND = "COMMAND_NOT_FOUND"
    PACKAGE_NOT_FOUND = "PACKAGE_NOT_FOUND"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    DNS_ERROR = "DNS_ERROR"
    PROXY_ERROR = "PROXY_ERROR"
    TLS_ERROR = "TLS_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PACKAGE_MANAGER_UNAVAILABLE = "PACKAGE_MANAGER_UNAVAILABLE"
    INSTALL_COMMAND_FAILED = "INSTALL_COMMAND_FAILED"
    VERSION_INCOMPATIBLE = "VERSION_INCOMPATIBLE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


@dataclass
class ToolProvider:
    """A tool, library, or engine providing a specific capability."""

    name: str
    technology: Technology
    capability: CapabilityType
    priority: ToolPriority
    source: str  # e.g. "CLI binary", "Python package", "Internal engine"
    license: str  # e.g. "Apache-2.0", "MIT", "GPL-3.0"
    real_command: Optional[str] = None  # Exact CLI command / subcommand verified
    install_method: InstallMethod = InstallMethod.MANUAL
    install_package_name: Optional[str] = None  # e.g. "ruff", "pyyaml", "checkov"
    offline_capable: bool = True
    install_hint: Optional[str] = None
    documentation_url: Optional[str] = None
    is_available_fn: Optional[Callable[[], bool]] = field(default=None, repr=False)
    version_fn: Optional[Callable[[], Optional[str]]] = field(default=None, repr=False)
    verify_fn: Optional[Callable[[], bool]] = field(default=None, repr=False)

    @property
    def is_available(self) -> bool:
        """Check if this provider is locally available."""
        if self.is_available_fn is not None:
            try:
                return bool(self.is_available_fn())
            except Exception:
                return False
        return True

    @property
    def version(self) -> Optional[str]:
        """Get the provider version if available."""
        if self.version_fn is not None:
            try:
                return self.version_fn()
            except Exception:
                return None
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "technology": self.technology.value,
            "capability": self.capability.value,
            "priority": int(self.priority),
            "priority_name": self.priority.name,
            "real_command": self.real_command,
            "install_method": self.install_method.value,
            "install_package_name": self.install_package_name,
            "source": self.source,
            "license": self.license,
            "available": self.is_available,
            "version": self.version,
            "offline_capable": self.offline_capable,
            "install_hint": self.install_hint,
            "documentation_url": self.documentation_url,
        }


@dataclass
class CapabilityResult:
    """Result of resolving a capability against the provider hierarchy."""

    capability: CapabilityType
    selected_provider: Optional[ToolProvider]
    priority: ToolPriority
    status: str  # "available", "manual_review", "configured_unavailable", "no_provider"
    all_providers: List[ToolProvider] = field(default_factory=list)
    fallback_chain: List[str] = field(default_factory=list)
    fallback_provider: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability.value,
            "selected_provider": self.selected_provider.to_dict() if self.selected_provider else None,
            "priority": int(self.priority),
            "priority_name": self.priority.name,
            "status": self.status,
            "reason": self.reason,
            "fallback_provider": self.fallback_provider,
            "message": self.message,
            "fallback_chain": self.fallback_chain,
            "available_providers": [p.to_dict() for p in self.all_providers],
        }


@dataclass
class InstallationResult:
    """Result of attempting to install or verify a tool provider."""

    tool_name: str
    technology: Technology
    status: str  # "success", "already_available", "failed", "skipped"
    error_kind: Optional[InstallationErrorKind] = None
    message: str = ""
    fallback_provider: Optional[str] = None
    version: Optional[str] = None
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "technology": self.technology.value,
            "status": self.status,
            "error_kind": self.error_kind.value if self.error_kind else None,
            "message": self.message,
            "fallback_provider": self.fallback_provider,
            "version": self.version,
            "verified": self.verified,
        }


@dataclass
class SetupReport:
    """Structured report of dependency and tool setup."""

    successful: List[InstallationResult] = field(default_factory=list)
    already_available: List[InstallationResult] = field(default_factory=list)
    failed: List[InstallationResult] = field(default_factory=list)
    skipped: List[InstallationResult] = field(default_factory=list)
    fallbacks: List[Dict[str, str]] = field(default_factory=list)

    @property
    def total_attempted(self) -> int:
        return len(self.successful) + len(self.failed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "successful": [r.to_dict() for r in self.successful],
            "already_available": [r.to_dict() for r in self.already_available],
            "failed": [r.to_dict() for r in self.failed],
            "skipped": [r.to_dict() for r in self.skipped],
            "fallbacks": self.fallbacks,
            "summary": {
                "total_successful": len(self.successful),
                "total_already_available": len(self.already_available),
                "total_failed": len(self.failed),
                "total_skipped": len(self.skipped),
            },
        }
