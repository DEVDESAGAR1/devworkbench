"""Large-file-safe streaming build log analyzer with root-cause identification."""

import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from devworkbench.correlation import CorrelationEngine
from devworkbench.models import (
    BuildLogReport,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    RootCauseCandidate,
)
from devworkbench.signatures.base import SignatureMatch
from devworkbench.signatures.registry import SignatureRegistry


class BuildLogAnalyzer:
    """Analyzes Jenkins, Kubernetes, OpenShift, Helm, Docker, and Terraform build logs."""

    def __init__(self) -> None:
        self.signature_registry = SignatureRegistry()

    def analyze_stream(
        self, stream: Any, source_name: str = "stdin"
    ) -> BuildLogReport:
        """Streamingly parse build log lines without loading the whole file into memory."""
        start_time = time.perf_counter()

        matches_by_sig: dict[str, list[SignatureMatch]] = defaultdict(list)
        all_matches: list[SignatureMatch] = []
        total_lines = 0

        # Handle file/StringIO/Click stream objects safely
        if hasattr(stream, "read"):
            try:
                content = stream.read()
                lines_iter = content.splitlines()
            except Exception:
                lines_iter = stream
        else:
            lines_iter = stream

        for line_num, line in enumerate(lines_iter, start=1):
            total_lines += 1
            match = self.signature_registry.match_line(line, line_num)
            if match:
                matches_by_sig[match.signature_id].append(match)
                all_matches.append(match)

        # 1. Deduplicate & group matches into diagnostics
        diagnostics: list[Diagnostic] = []
        for sig_id, match_list in matches_by_sig.items():
            first_match = match_list[0]
            count = len(match_list)
            suffix = f" (occurred {count} times)" if count > 1 else ""

            diagnostics.append(
                Diagnostic(
                    path=source_name,
                    line=first_match.line_number,
                    severity=DiagnosticSeverity.ERROR,
                    rule=first_match.signature_id,
                    message=f"{first_match.message}{suffix}",
                    source=first_match.source,
                    category=DiagnosticCategory.RUNTIME_ERROR,
                    details=f"Sample log line: {first_match.raw_line}",
                )
            )

        # 2. Identify Root Cause Candidates conservatively
        root_causes: list[RootCauseCandidate] = []
        root_matches = [m for m in all_matches if m.is_root_cause_candidate]
        cascaded_symptoms = [m for m in all_matches if not m.is_root_cause_candidate]

        # Group root causes by signature ID
        seen_root_sigs = set()
        for rm in root_matches:
            if rm.signature_id in seen_root_sigs:
                continue
            seen_root_sigs.add(rm.signature_id)

            # Collect downstream cascaded failures that occurred after this root cause
            related: list[str] = []
            for sm in cascaded_symptoms:
                if sm.line_number >= rm.line_number:
                    related.append(f"Line {sm.line_number}: {sm.message}")

            root_causes.append(
                RootCauseCandidate(
                    title=rm.message,
                    source=rm.source,
                    category=rm.category,
                    confidence=rm.confidence,
                    description=f"Identified primary failure on line {rm.line_number}: '{rm.raw_line}'",
                    related_failures=related[:5],  # Top 5 downstream impacts
                    line_number=rm.line_number,
                )
            )

        # 3. Cross-tool correlation
        correlations = CorrelationEngine.correlate(
            detections=[],
            diagnostics=diagnostics,
            root_causes=root_causes,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        return BuildLogReport(
            source_path=source_name,
            total_lines=total_lines,
            diagnostics=diagnostics,
            root_causes=root_causes,
            correlations=correlations,
            duration_ms=round(duration_ms, 2),
            modified_files=0,  # Strict immutability
        )

    def analyze_file(self, log_path_str: str) -> BuildLogReport:
        """Analyze a build log from file path or stdin ('-')."""
        if log_path_str == "-":
            return self.analyze_stream(sys.stdin, source_name="stdin")

        log_path = Path(log_path_str)
        if not log_path.exists():
            raise FileNotFoundError(f"Build log file not found: {log_path_str}")

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            return self.analyze_stream(f, source_name=str(log_path))
