"""Diagnostic deduplication engine to prevent redundant findings across overlapping tools."""

import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from devworkbench.models import Diagnostic, DiagnosticCategory, DiagnosticSeverity


class DiagnosticDeduplicator:
    """Intelligently deduplicates findings when multiple engines inspect the same file."""

    # Priority of sources when duplicate findings exist for the same line/issue
    SOURCE_PRIORITY: Dict[str, int] = {
        "ruff": 10,
        "hadolint": 10,
        "actionlint": 10,
        "ansible-lint": 10,
        "kube-linter": 10,
        "kubeconform": 10,
        "tflint": 10,
        "checkov": 10,
        "shellcheck": 10,
        "helm-lint": 10,
        "helm-template": 10,
        "terraform": 8,
        "yamllint": 8,
        "pyyaml": 6,
        "python-ast": 6,
        "k8s-rules": 5,
        "openshift-rules": 5,
        "jenkins-rules": 5,
        "helm-rules": 5,
        "generic": 1,
    }

    @classmethod
    def _normalize_message_key(cls, msg: str) -> str:
        """Create a simplified fingerprint of an error message."""
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", msg.lower())
        # Truncate to first 40 alphanumeric characters to capture core intent
        return cleaned[:40]

    @classmethod
    def deduplicate(cls, diagnostics: List[Diagnostic]) -> List[Diagnostic]:
        """Deduplicate diagnostics while preserving the highest-fidelity source and detail."""
        if not diagnostics:
            return []

        # Group by (path, line, category, normalized_msg_key)
        grouped: Dict[Tuple[str, int, str, str], List[Diagnostic]] = defaultdict(list)
        unpositioned: List[Diagnostic] = []

        for diag in diagnostics:
            if diag.line is None:
                # File-level diagnostic without line number
                norm_msg = cls._normalize_message_key(diag.message)
                grouped[(diag.path, -1, diag.category.value, norm_msg)].append(diag)
            else:
                norm_msg = cls._normalize_message_key(diag.message)
                grouped[(diag.path, diag.line, diag.category.value, norm_msg)].append(diag)

        deduplicated: List[Diagnostic] = []

        for key, diags in grouped.items():
            if len(diags) == 1:
                deduplicated.append(diags[0])
            else:
                # Sort by source priority and presence of specific rule ID
                best = max(
                    diags,
                    key=lambda d: (
                        cls.SOURCE_PRIORITY.get(d.source.lower(), 0),
                        1 if d.rule else 0,
                        1 if d.column else 0,
                    ),
                )
                contributors = []
                for d in diags:
                    if d is not best:
                        src_label = f"{d.source}" + (f" [{d.rule}]" if d.rule else "")
                        if src_label not in contributors:
                            contributors.append(src_label)
                best.contributing_sources = contributors
                deduplicated.append(best)

        # Sort deduplicated diagnostics by (path, line, column)
        deduplicated.sort(
            key=lambda d: (
                d.path,
                d.line if d.line is not None else -1,
                d.column if d.column is not None else -1,
            )
        )
        return deduplicated
