"""Terraform and IaC security and best-practice rules."""

import re
from pathlib import Path
from typing import Any

from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
)
from devworkbench.rules.base import BaseRule, RuleMetadata


class TerraformHardcodedSecretRule(BaseRule):
    """TERRAFORM001: Detects hard-coded cloud API keys / secrets in Terraform files."""

    RE_SECRET_PATTERN = re.compile(
        r"""(?i)(?:access_key|secret_key|api_key|token|password)\s*=\s*['"]([A-Za-z0-9/+=]{16,})['"]"""
    )

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="TERRAFORM001",
            technology=Technology.TERRAFORM,
            severity=DiagnosticSeverity.ERROR,
            category=DiagnosticCategory.SECURITY,
            description="Hard-coded cloud credential or secret token detected in Terraform configuration.",
            rationale="Committing access keys or secrets in HCL files exposes infrastructure to unauthorized control.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://developer.hashicorp.com/terraform/tutorials/configuration-language/sensitive-variables",
            help_url="https://developer.hashicorp.com/terraform/tutorials/configuration-language/sensitive-variables",
            autofix_supported=False,
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            if self.RE_SECRET_PATTERN.search(line):
                diagnostics.append(
                    Diagnostic(
                        path=detection.relative_path,
                        line=line_num,
                        severity=self.metadata.severity,
                        rule=self.metadata.rule_id,
                        message="Potential hard-coded secret detected in Terraform file. Use variables with sensitive=true or environment variables instead.",
                        source="terraform-rules",
                        category=self.metadata.category,
                        provider=self.metadata.provider,
                        provider_priority=self.metadata.provider_priority,
                        provider_type="devworkbench",
                        rule_origin=self.metadata.rule_origin,
                        documentation_url=self.metadata.documentation_url,
                    )
                )
        return diagnostics
