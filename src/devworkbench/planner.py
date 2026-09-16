"""Fix planner and conflict detection engine for DevWorkBench."""

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

from devworkbench.models import (
    Diagnostic,
    FixCandidate,
    FixConflict,
    FixKind,
    FixPlan,
    FixSafety,
)


class FixPlanner:
    """Plans safe fix execution, evaluates safety, and detects conflicts."""

    @classmethod
    def _compute_sha256(cls, file_path: Path) -> str:
        """Compute the SHA-256 hash of a file's current bytes."""
        try:
            return hashlib.sha256(file_path.read_bytes()).hexdigest()
        except Exception:
            return ""

    @classmethod
    def create_plan(
        cls,
        diagnostics: List[Diagnostic],
        target_paths: List[str],
        base_dir: Path = Path("."),
    ) -> FixPlan:
        """Analyze diagnostics, classify candidates, detect conflicts, and generate a FixPlan."""
        safe_candidates: List[FixCandidate] = []
        manual_candidates: List[FixCandidate] = []
        conflicts: List[FixConflict] = []

        # 1. Categorize diagnostics into safe candidates vs manual review
        for diag in diagnostics:
            is_safe = (
                diag.fix_available
                and diag.fix_safety == FixSafety.SAFE
                and diag.fix_kind in [FixKind.NATIVE_ENGINE, FixKind.DEVWORKBENCH_SAFE]
            )

            desc = diag.fix_description or f"Fix for {diag.rule or diag.message}"
            cand = FixCandidate(
                path=diag.path,
                rule=diag.rule,
                message=diag.message,
                source=diag.fix_source or diag.source,
                fix_kind=diag.fix_kind if is_safe else FixKind.MANUAL,
                fix_safety=diag.fix_safety if is_safe else FixSafety.REVIEW_REQUIRED,
                description=desc,
                line=diag.line,
                column=diag.column,
            )

            if is_safe:
                safe_candidates.append(cand)
            else:
                manual_candidates.append(cand)

        # 2. Conflict Detection: group safe candidates by file path
        by_file: Dict[str, List[FixCandidate]] = defaultdict(list)
        for c in safe_candidates:
            by_file[c.path].append(c)

        valid_safe_candidates: List[FixCandidate] = []
        files_to_modify: Set[str] = set()

        for path_str, file_candidates in by_file.items():
            # Check for multi-engine collision: different distinct external tool sources
            sources = {c.source for c in file_candidates}
            # Ruff and ruff-format are same tool family; terraform and tofu are same family
            normalized_sources = set()
            for s in sources:
                s_lower = s.lower()
                if "ruff" in s_lower:
                    normalized_sources.add("ruff")
                elif "terraform" in s_lower or "tofu" in s_lower:
                    normalized_sources.add("terraform")
                else:
                    normalized_sources.add(s_lower)

            if len(normalized_sources) > 1:
                # Conflict detected: Multiple different engines trying to modify the same file
                conflicts.append(
                    FixConflict(
                        path=path_str,
                        reason=f"Multiple conflicting fix engines ({', '.join(sources)}) targeting the same file.",
                        candidates=file_candidates,
                    )
                )
                # Move to manual candidates for safety
                manual_candidates.extend(file_candidates)
            else:
                valid_safe_candidates.extend(file_candidates)
                files_to_modify.add(path_str)

        # 3. Capture SHA-256 pre-modification fingerprints
        file_hashes: Dict[str, str] = {}
        for p_str in files_to_modify:
            # Resolve relative or absolute path
            p_obj = Path(p_str)
            if not p_obj.is_absolute():
                p_obj = base_dir / p_str
            if p_obj.is_file():
                file_hashes[p_str] = cls._compute_sha256(p_obj)

        return FixPlan(
            target_paths=target_paths,
            safe_candidates=valid_safe_candidates,
            manual_candidates=manual_candidates,
            conflicts=conflicts,
            files_to_modify=sorted(list(files_to_modify)),
            file_hashes_before=file_hashes,
        )
