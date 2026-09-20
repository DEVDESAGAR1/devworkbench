"""Dockerfile best-practice and reliability rules."""

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


class DockerLatestImageRule(BaseRule):
    """DOCKER001: Warns if FROM base image uses unpinned or :latest tag."""

    RE_FROM = re.compile(r"""^FROM\s+([^\s]+)""", re.MULTILINE | re.IGNORECASE)

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="DOCKER001",
            technology=Technology.DOCKERFILE,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Base image uses unpinned or ':latest' tag in FROM instruction.",
            rationale="Using unpinned base images can lead to non-reproducible container builds when base layers are updated upstream.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://docs.docker.com/develop/develop-images/instructions/#from",
            help_url="https://docs.docker.com/develop/develop-images/instructions/#from",
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
            m = self.RE_FROM.match(line.strip())
            if m:
                img = m.group(1).strip()
                if img.lower() == "scratch":
                    continue
                if img.endswith(":latest") or (":" not in img and "@" not in img):
                    diagnostics.append(
                        Diagnostic(
                            path=detection.relative_path,
                            line=line_num,
                            severity=self.metadata.severity,
                            rule=self.metadata.rule_id,
                            message=f"Base image '{img}' uses unpinned tag. Pin image version or SHA digest.",
                            source="docker-rules",
                            category=self.metadata.category,
                            provider=self.metadata.provider,
                            provider_priority=self.metadata.provider_priority,
                            provider_type="devworkbench",
                            rule_origin=self.metadata.rule_origin,
                            documentation_url=self.metadata.documentation_url,
                        )
                    )
        return diagnostics
