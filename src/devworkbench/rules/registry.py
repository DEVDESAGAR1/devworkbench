"""Registry for managing and evaluating DevOps best-practice rules."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from devworkbench.models import Diagnostic, FileDetection, Technology
from devworkbench.rules.base import BaseRule
from devworkbench.rules.docker import DockerLatestImageRule
from devworkbench.rules.helm import HelmChartMaintainersRule, HelmChartMetadataRule
from devworkbench.rules.jenkins import (
    JenkinsCredentialRule,
    JenkinsMissingTimeoutRule,
    JenkinsShellErrorSuppressionRule,
    JenkinsUnsafeShellInterpolationRule,
)
from devworkbench.rules.kubernetes import (
    K8sLatestImageTagRule,
    K8sMissingProbesRule,
    K8sPrivilegedContainerRule,
    K8sResourceLimitsRule,
)
from devworkbench.rules.openshift import OpenShiftInsecureRouteRule
from devworkbench.rules.terraform import TerraformHardcodedSecretRule


class RuleRegistry:
    """Registry collecting and evaluating all DevOps best-practice rules."""

    def __init__(self) -> None:
        self.rules: List[BaseRule] = [
            JenkinsCredentialRule(),
            JenkinsUnsafeShellInterpolationRule(),
            JenkinsMissingTimeoutRule(),
            JenkinsShellErrorSuppressionRule(),
            K8sResourceLimitsRule(),
            K8sPrivilegedContainerRule(),
            K8sLatestImageTagRule(),
            K8sMissingProbesRule(),
            OpenShiftInsecureRouteRule(),
            HelmChartMetadataRule(),
            HelmChartMaintainersRule(),
            DockerLatestImageRule(),
            TerraformHardcodedSecretRule(),
        ]

    def evaluate_rules(
        self,
        file_path: Path,
        detection: FileDetection,
        content: Optional[str] = None,
        parsed_data: Optional[Any] = None,
    ) -> List[Diagnostic]:
        """Evaluate all relevant rules for a file detection."""
        diagnostics: List[Diagnostic] = []

        # Find rules matching file technology or related technologies
        relevant_rules = [
            rule for rule in self.rules
            if rule.metadata.technology == detection.technology
        ]

        if not relevant_rules:
            return diagnostics

        if content is None:
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = file_path.read_text(encoding="latin-1", errors="ignore")
                except Exception:
                    return diagnostics

        for rule in relevant_rules:
            try:
                diags = rule.evaluate(
                    file_path=file_path,
                    content=content,
                    detection=detection,
                    parsed_data=parsed_data,
                )
                diagnostics.extend(diags)
            except Exception:
                pass

        return diagnostics
