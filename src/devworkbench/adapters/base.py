"""Base Adapter interface for technology-specific tooling in DevWorkBench."""

import functools
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from devworkbench.models import (
    CommandExecution,
    Diagnostic,
    FileDetection,
    FixCandidate,
    HelmChart,
    Technology,
    ToolWarning,
)


class BaseAdapter(ABC):
    """Abstract base class for all technology adapters.

    Each adapter encapsulates tool invocation (detect, format, lint, validate, analyze)
    for a specific technology while returning normalized diagnostics.
    """

    def __init__(self) -> None:
        self.executions: List[CommandExecution] = []

    def record_execution(self, execution: CommandExecution) -> None:
        """Record an execution telemetry object."""
        self.executions.append(execution)

    def get_executions(self) -> List[CommandExecution]:
        """Retrieve all recorded executions."""
        return list(self.executions)

    def clear_executions(self) -> None:
        """Clear recorded executions for a new run."""
        self.executions.clear()

    @staticmethod
    def find_tool(tool_name: str) -> Optional[str]:
        """Find tool executable in PATH."""
        return shutil.which(tool_name)

    @property
    @abstractmethod
    def technology(self) -> Technology:
        """The technology managed by this adapter."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""
        pass

    def can_handle(self, detection: FileDetection) -> bool:
        """Return True if this adapter can process the detected file."""
        return detection.technology == self.technology

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        """Check if required external engines/tools are available.

        Returns:
            (True, None) if ready, or (False, ToolWarning) with install instructions.
        """
        return True, None

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        """Analyze an individual file and return normalized diagnostics.

        Must NEVER modify the file.
        """
        return []

    def analyze_project(
        self, project_path: Path, chart: Optional[HelmChart] = None
    ) -> List[Diagnostic]:
        """Analyze a project-level entity (such as a Helm chart directory).

        Must NEVER modify any files.
        """
        return []

    def apply_fix(self, file_path: Path, candidate: FixCandidate) -> Tuple[bool, Optional[str]]:
        """Apply a safe native fix to the target file.

        Args:
            file_path: Absolute path to the file to modify.
            candidate: Proposed FixCandidate to execute.

        Returns:
            (success: bool, error_message: Optional[str])
        """
        return False, f"Native fix not supported by {self.name}"

    # Optional granular lifecycle methods
    def format(self, file_path: Path, check_only: bool = True) -> Dict[str, Any]:
        """Format check only."""
        raise NotImplementedError(f"Format not implemented for {self.name}")

    def lint(self, file_path: Path) -> List[Diagnostic]:
        """Lint check."""
        raise NotImplementedError(f"Lint not implemented for {self.name}")

    def validate(self, file_path: Path) -> List[Diagnostic]:
        """Syntax / Schema validation."""
        raise NotImplementedError(f"Validate not implemented for {self.name}")
