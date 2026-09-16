"""OpenShift specific best-practice and security rules."""

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


class OpenShiftInsecureRouteRule(BaseRule):
    """OPENSHIFT001: Warns on OpenShift Routes without TLS termination configured."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="OPENSHIFT001",
            technology=Technology.OPENSHIFT,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.SECURITY,
            description="OpenShift Route lacks TLS termination configuration.",
            rationale="Unencrypted HTTP Routes expose ingress traffic to eavesdropping and man-in-the-middle attacks.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://docs.openshift.com/container-platform/latest/networking/routes/secured-routes.html",
            help_url="https://docs.openshift.com/container-platform/latest/networking/routes/secured-routes.html",
            autofix_supported=False,
            false_positive_notes="Internal testing routes in isolated non-production environments may omit TLS.",
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Optional[Any] = None,
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        try:
            docs = list(yaml.safe_load_all(content)) if parsed_data is None else [parsed_data]
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("kind", "")
                if kind == "Route":
                    spec = doc.get("spec", {})
                    if "tls" not in spec:
                        diagnostics.append(
                            Diagnostic(
                                path=detection.relative_path,
                                severity=self.metadata.severity,
                                rule=self.metadata.rule_id,
                                message="OpenShift Route has no TLS configuration. Consider adding edge, reencrypt, or passthrough TLS termination.",
                                source="openshift-rules",
                                category=self.metadata.category,
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
