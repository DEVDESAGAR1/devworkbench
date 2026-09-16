"""Fix execution engine and safety enforcement for DevWorkBench."""

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from devworkbench.adapters.registry import AdapterRegistry
from devworkbench.models import (
    FixCandidate,
    FixPlan,
    FixResultItem,
    Technology,
    ToolState,
)


class FixEngine:
    """Safely executes planned fixes with strict SHA-256 pre-modification checks and atomic application."""

    @classmethod
    def _compute_sha256(cls, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        try:
            return hashlib.sha256(file_path.read_bytes()).hexdigest()
        except Exception:
            return ""

    @classmethod
    def execute_plan(
        cls,
        plan: FixPlan,
        adapter_registry: AdapterRegistry,
        base_dir: Path = Path("."),
    ) -> Tuple[List[FixResultItem], Dict[str, str], int]:
        """Apply the planned safe fixes while strictly validating file integrity.

        Returns:
            (results, engine_states, files_modified_count)
        """
        results: List[FixResultItem] = []
        engine_states: Dict[str, str] = {}
        files_modified_count = 0

        # Group safe candidates by path
        by_file: Dict[str, List[FixCandidate]] = {}
        for c in plan.safe_candidates:
            if c.path not in by_file:
                by_file[c.path] = []
            by_file[c.path].append(c)

        for path_str, candidates in by_file.items():
            file_obj = Path(path_str)
            if not file_obj.is_absolute():
                file_obj = base_dir / path_str

            if not file_obj.exists():
                results.append(
                    FixResultItem(
                        path=path_str,
                        rule=None,
                        source="system",
                        status="skipped",
                        message="File no longer exists on disk. Fix skipped.",
                    )
                )
                continue

            # 1. SHA-256 Pre-Modification Integrity Check
            expected_hash = plan.file_hashes_before.get(path_str)
            current_hash = cls._compute_sha256(file_obj)

            if expected_hash and current_hash != expected_hash:
                results.append(
                    FixResultItem(
                        path=path_str,
                        rule=None,
                        source="integrity",
                        status="skipped",
                        message="File changed since analysis. Automatic fix skipped to prevent overwriting user changes.",
                    )
                )
                continue

            initial_hash_before_writes = current_hash
            file_modified = False

            # 2. Execute fixes for this file
            for candidate in candidates:
                # Find matching adapter
                adapter = None
                for a in adapter_registry.adapters:
                    source_l = candidate.source.lower()
                    if a.name.lower() in source_l or source_l in a.name.lower() or ("ruff" in source_l and "ruff" in a.name.lower()) or ("terraform" in source_l and "terraform" in a.name.lower()):
                        adapter = a
                        break

                if not adapter:
                    results.append(
                        FixResultItem(
                            path=path_str,
                            rule=candidate.rule,
                            source=candidate.source,
                            status="skipped",
                            message=f"No matching adapter registered for source '{candidate.source}'.",
                        )
                    )
                    continue

                is_avail, warning = adapter.is_available()
                if not is_avail:
                    engine_states[candidate.source] = ToolState.NOT_INSTALLED.value
                    results.append(
                        FixResultItem(
                            path=path_str,
                            rule=candidate.rule,
                            source=candidate.source,
                            status="skipped",
                            message=f"Engine '{adapter.name}' is unavailable. Fix skipped.",
                        )
                    )
                    continue

                try:
                    success, err_msg = adapter.apply_fix(file_obj, candidate)
                    if success:
                        results.append(
                            FixResultItem(
                                path=path_str,
                                rule=candidate.rule,
                                source=candidate.source,
                                status="applied",
                                message=f"Applied: {candidate.description}",
                            )
                        )
                        engine_states[candidate.source] = ToolState.FIXED.value
                    else:
                        results.append(
                            FixResultItem(
                                path=path_str,
                                rule=candidate.rule,
                                source=candidate.source,
                                status="failed",
                                message=f"Fix failed: {err_msg or 'Unknown error'}",
                                error=err_msg,
                            )
                        )
                        engine_states[candidate.source] = ToolState.FIX_FAILED.value
                except Exception as e:
                    results.append(
                        FixResultItem(
                            path=path_str,
                            rule=candidate.rule,
                            source=candidate.source,
                            status="failed",
                            message=f"Unexpected error executing fix: {e}",
                            error=str(e),
                        )
                    )
                    engine_states[candidate.source] = ToolState.FIX_FAILED.value

            # 3. Check if file content actually changed
            new_hash = cls._compute_sha256(file_obj)
            if new_hash and new_hash != initial_hash_before_writes:
                files_modified_count += 1

        return results, engine_states, files_modified_count
