"""Base Rule definitions for DevOps best-practice checks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    FixSafety,
    Technology,
)


@dataclass
class RuleMetadata:
    """Metadata describing a DevOps best-practice rule."""

    rule_id: str
    technology: Technology
    severity: DiagnosticSeverity
    category: DiagnosticCategory
    description: str
    rationale: Optional[str] = None
    provider: str = "devworkbench"
    provider_priority: int = 3
    rule_origin: str = "DevWorkBench rule engine"
    documentation_url: Optional[str] = None
    help_url: Optional[str] = None
    autofix_supported: bool = False
    fix_available: bool = False
    fix_safety: Optional[FixSafety] = None
    false_positive_notes: Optional[str] = None


class BaseRule(ABC):
    """Abstract base class for all DevOps best-practice rules."""

    @property
    @abstractmethod
    def metadata(self) -> RuleMetadata:
        """Rule metadata."""
        pass

    @abstractmethod
    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Optional[Any] = None,
    ) -> List[Diagnostic]:
        """Evaluate rule against file and return any diagnostics."""
        pass
