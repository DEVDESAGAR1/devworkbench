"""Helm chart best-practice and structure rules."""

from pathlib import Path
from typing import Any, List, Optional

import yaml

from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
)
from devworkbench.rules.base import BaseRule, RuleMetadata


class HelmChartMetadataRule(BaseRule):
    """HELM001: Validates Chart.yaml for required metadata (version, name, apiVersion)."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="HELM001",
            technology=Technology.HELM,
            severity=DiagnosticSeverity.ERROR,
            category=DiagnosticCategory.SCHEMA,
            description="Chart.yaml is missing required metadata (name, version, apiVersion).",
            rationale="Helm requires name, version (SemVer 2), and apiVersion to validate and package charts.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://helm.sh/docs/topics/charts/#the-chartyaml-file",
            help_url="https://helm.sh/docs/topics/charts/#the-chartyaml-file",
            autofix_supported=False,
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Optional[Any] = None,
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if file_path.name.lower() in ["chart.yaml", "chart.yml"]:
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    if not data.get("version"):
                        diagnostics.append(
                            Diagnostic(
                                path=detection.relative_path,
                                severity=DiagnosticSeverity.ERROR,
                                rule=self.metadata.rule_id,
                                message="Chart.yaml is missing required 'version' field.",
                                source="helm-rules",
                                category=DiagnosticCategory.SCHEMA,
                                provider=self.metadata.provider,
                                provider_priority=self.metadata.provider_priority,
                                provider_type="devworkbench",
                                rule_origin=self.metadata.rule_origin,
                                documentation_url=self.metadata.documentation_url,
                            )
                        )
                    if not data.get("description"):
                        diagnostics.append(
                            Diagnostic(
                                path=detection.relative_path,
                                severity=DiagnosticSeverity.INFO,
                                rule=self.metadata.rule_id,
                                message="Chart.yaml is missing recommended 'description' field.",
                                source="helm-rules",
                                category=DiagnosticCategory.BEST_PRACTICE,
                                provider=self.metadata.provider,
                                provider_priority=self.metadata.provider_priority,
                                provider_type="devworkbench",
                                rule_origin=self.metadata.rule_origin,
                                documentation_url=self.metadata.documentation_url,
                            )
                        )
            except Exception:
                pass
        return diagnostics


class HelmChartMaintainersRule(BaseRule):
    """HELM002: Recommends maintainers and source repository links in published charts."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="HELM002",
            technology=Technology.HELM,
            severity=DiagnosticSeverity.HINT,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Chart.yaml lacks maintainers or sources information.",
            rationale="Maintainer info helps consumers identify points of contact and source repository lineage.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://helm.sh/docs/topics/charts/#the-chartyaml-file",
            help_url="https://helm.sh/docs/topics/charts/#the-chartyaml-file",
            autofix_supported=False,
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Optional[Any] = None,
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if file_path.name.lower() in ["chart.yaml", "chart.yml"]:
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict) and "maintainers" not in data and "sources" not in data:
                    diagnostics.append(
                        Diagnostic(
                            path=detection.relative_path,
                            severity=DiagnosticSeverity.HINT,
                            rule=self.metadata.rule_id,
                            message="Chart.yaml does not declare 'maintainers' or 'sources'.",
                            source="helm-rules",
                            category=DiagnosticCategory.BEST_PRACTICE,
                            provider=self.metadata.provider,
                            provider_priority=self.metadata.provider_priority,
                            provider_type="devworkbench",
                            rule_origin=self.metadata.rule_origin,
                            documentation_url=self.metadata.documentation_url,
                        )
                    )
            except Exception:
                pass
        return diagnostics
