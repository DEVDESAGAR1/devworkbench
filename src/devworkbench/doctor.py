"""Environment diagnostic and health inspection engine."""

import importlib.metadata
import importlib.util
import platform
import sys
from dataclasses import dataclass, field
from typing import Any

from devworkbench import __version__
from devworkbench.capabilities.model import ToolPriority
from devworkbench.capabilities.registry import CapabilityRegistry
from devworkbench.capabilities.resolver import CapabilityResolver


@dataclass
class DependencyStatus:
    """Status of a Python runtime dependency."""

    name: str
    available: bool
    version: str | None = None
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "required": self.required,
        }


@dataclass
class ExternalToolStatus:
    """Status of an external CLI tool or analyzer."""

    name: str
    available: bool
    version: str | None = None
    source: str = "CLI binary"
    license: str = "Unknown"
    install_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "source": self.source,
            "license": self.license,
            "install_hint": self.install_hint,
        }


@dataclass
class DoctorDiagnostic:
    """Comprehensive environment and diagnostic health report."""

    devworkbench_version: str
    python_version: str
    platform_name: str
    platform_release: str
    architecture: str
    python_executable: str
    core_dependencies: list[DependencyStatus] = field(default_factory=list)
    external_tools: list[ExternalToolStatus] = field(default_factory=list)
    capability_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": {
                "devworkbench_version": self.devworkbench_version,
                "python_version": self.python_version,
                "platform": self.platform_name,
                "release": self.platform_release,
                "architecture": self.architecture,
                "executable": self.python_executable,
            },
            "core_dependencies": [d.to_dict() for d in self.core_dependencies],
            "external_tools": [t.to_dict() for t in self.external_tools],
            "capability_summary": self.capability_summary,
        }


class DoctorEngine:
    """Executes offline system, dependency, and tool health diagnostics."""

    @staticmethod
    def _check_python_package(pkg_name: str, import_name: str | None = None) -> DependencyStatus:
        """Check if a Python package is available and probe its version."""
        imp = import_name or pkg_name
        available = importlib.util.find_spec(imp) is not None
        version = None
        if available:
            try:
                version = importlib.metadata.version(pkg_name)
            except Exception:
                try:
                    mod = sys.modules.get(imp) or __import__(imp)
                    version = getattr(mod, "__version__", None)
                except Exception:
                    version = "available"
        return DependencyStatus(
            name=pkg_name,
            available=available,
            version=version,
            required=True,
        )

    @classmethod
    def diagnose(cls, registry: CapabilityRegistry | None = None) -> DoctorDiagnostic:
        """Run complete doctor health diagnostics."""
        reg = registry or CapabilityRegistry()
        resolver = CapabilityResolver(reg)
        resolved_caps = resolver.resolve_all()

        # 1. Core Python dependencies
        core_deps = [
            cls._check_python_package("click"),
            cls._check_python_package("rich"),
            cls._check_python_package("pyyaml", "yaml"),
        ]

        # 2. External tools from registry
        external_tools: list[ExternalToolStatus] = []
        seen_tools = set()

        for provider in reg.providers:
            if provider.name in seen_tools:
                continue
            seen_tools.add(provider.name)
            external_tools.append(ExternalToolStatus(
                name=provider.name,
                available=provider.is_available,
                version=provider.version,
                source=provider.source,
                license=provider.license,
                install_hint=provider.install_hint,
            ))

        # 3. Capability priority breakdown
        summary_counts = {
            "total_capabilities": len(resolved_caps),
            "native_active": sum(1 for r in resolved_caps.values() if r.status == "available" and r.priority == ToolPriority.NATIVE),
            "opensource_active": sum(1 for r in resolved_caps.values() if r.status == "available" and r.priority == ToolPriority.OPENSOURCE),
            "devworkbench_active": sum(1 for r in resolved_caps.values() if r.status == "available" and r.priority == ToolPriority.DEVWORKBENCH),
            "manual_review_required": sum(1 for r in resolved_caps.values() if r.status in ["manual_review", "configured_unavailable", "no_provider"]),
        }

        return DoctorDiagnostic(
            devworkbench_version=__version__,
            python_version=platform.python_version(),
            platform_name=platform.system(),
            platform_release=platform.release(),
            architecture=platform.machine(),
            python_executable=sys.executable,
            core_dependencies=core_deps,
            external_tools=external_tools,
            capability_summary=summary_counts,
        )
