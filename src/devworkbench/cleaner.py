"""Kubernetes manifest cleaner engine for DevWorkBench.

Removes runtime status, managed fields, internal metadata, and annotations
using kubectl-neat if available or internal deterministic resource-aware cleaning.
"""

import difflib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from devworkbench.execution import CommandRunner
from devworkbench.models import CleanupResult, CommandExecution

# Metadata fields that are purely server-side/runtime state in Kubernetes
RUNTIME_METADATA_FIELDS = {
    "managedFields",
    "generation",
    "resourceVersion",
    "uid",
    "creationTimestamp",
    "selfLink",
    "deletionTimestamp",
    "deletionGracePeriodSeconds",
}

# Runtime status and node-specific top-level blocks
RUNTIME_TOP_LEVEL_FIELDS = {
    "status",
}


class ManifestCleaner:
    """Resource-aware cleaner for Kubernetes YAML manifests."""

    @staticmethod
    def _clean_dict(doc: Dict[str, Any], removed_fields: List[str]) -> Dict[str, Any]:
        """Recursively clean runtime and internal fields from a Kubernetes manifest dictionary."""
        if not isinstance(doc, dict):
            return doc

        cleaned: Dict[str, Any] = {}

        for k, v in doc.items():
            # Check top-level runtime fields
            if k in RUNTIME_TOP_LEVEL_FIELDS:
                removed_fields.append(f"root.{k}")
                continue

            if k == "metadata" and isinstance(v, dict):
                cleaned_meta: Dict[str, Any] = {}
                for m_k, m_v in v.items():
                    if m_k in RUNTIME_METADATA_FIELDS:
                        removed_fields.append(f"metadata.{m_k}")
                        continue
                    if m_k == "annotations" and isinstance(m_v, dict):
                        # Filter out ephemeral deployment / status annotations
                        cleaned_ann = {
                            ann_k: ann_v
                            for ann_k, ann_v in m_v.items()
                            if not ann_k.startswith("deployment.kubernetes.io/revision")
                        }
                        if cleaned_ann:
                            cleaned_meta[m_k] = cleaned_ann
                        else:
                            removed_fields.append("metadata.annotations (empty after filtering)")
                    else:
                        cleaned_meta[m_k] = m_v
                cleaned[k] = cleaned_meta
            elif isinstance(v, dict):
                cleaned[k] = ManifestCleaner._clean_dict(v, removed_fields)
            elif isinstance(v, list):
                cleaned[k] = [
                    ManifestCleaner._clean_dict(item, removed_fields) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                cleaned[k] = v

        return cleaned

    @classmethod
    def clean(
        cls,
        content_or_path: Union[str, Path],
        write_output_path: Optional[Path] = None,
        use_external_tool: bool = True,
    ) -> CleanupResult:
        """Clean a Kubernetes manifest from file or raw string content."""
        source_label = "stdin"
        raw_content = ""

        if isinstance(content_or_path, Path) or (isinstance(content_or_path, str) and (Path(content_or_path).is_file() or "\n" not in content_or_path)):
            p = Path(content_or_path)
            if p.is_file():
                source_label = str(p)
                raw_content = p.read_text(encoding="utf-8")
            else:
                raw_content = str(content_or_path)
        else:
            raw_content = str(content_or_path)

        removed_fields: List[str] = []
        cleaned_yaml = ""
        engine_used = "internal"
        execution: Optional[CommandExecution] = None

        # Try kubectl-neat if available and requested
        kubectl_neat_bin = shutil.which("kubectl-neat") or shutil.which("kubectl_neat")
        if use_external_tool and kubectl_neat_bin:
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", encoding="utf-8", delete=False) as tf:
                tf.write(raw_content)
                temp_file_path = tf.name

            try:
                exec_res = CommandRunner.run_command(
                    executable=kubectl_neat_bin,
                    args=["-f", temp_file_path],
                    technology="Kubernetes",
                    capability="kubernetes_cleanup",
                    provider_type="opensource",
                    provider_name="kubectl-neat",
                    cwd=Path.cwd(),
                    timeout_seconds=10.0,
                )
                execution = exec_res
                if exec_res.exit_code == 0 and exec_res.stdout.strip():
                    cleaned_yaml = exec_res.stdout.strip()
                    engine_used = "kubectl-neat"
                    removed_fields.append("Cleaned via kubectl-neat runtime field stripper")
            finally:
                try:
                    Path(temp_file_path).unlink(missing_ok=True)
                except Exception:
                    pass

        # Fallback to internal deterministic cleaner
        if not cleaned_yaml:
            try:
                docs = list(yaml.safe_load_all(raw_content))
                cleaned_docs = []
                for d in docs:
                    if d:
                        cleaned_docs.append(cls._clean_dict(d, removed_fields))
                    else:
                        cleaned_docs.append(d)

                if len(cleaned_docs) == 1:
                    cleaned_yaml = yaml.dump(cleaned_docs[0], sort_keys=False).strip()
                else:
                    cleaned_yaml = yaml.dump_all(cleaned_docs, sort_keys=False).strip()
                engine_used = "internal"
            except Exception as e:
                cleaned_yaml = raw_content
                removed_fields.append(f"Parsing error, output unmodified: {e}")

        # Compute diff
        diff_lines = list(
            difflib.unified_diff(
                raw_content.splitlines(keepends=True),
                cleaned_yaml.splitlines(keepends=True),
                fromfile=f"a/{source_label}",
                tofile=f"b/{source_label} (cleaned)",
            )
        )
        diff_text = "".join(diff_lines)

        # Validate that cleaned YAML is structurally sound
        validation_passed = True
        try:
            list(yaml.safe_load_all(cleaned_yaml))
        except Exception:
            validation_passed = False

        written = False
        out_str = None
        if write_output_path:
            write_output_path.write_text(cleaned_yaml + "\n", encoding="utf-8")
            written = True
            out_str = str(write_output_path)

        return CleanupResult(
            source_path=source_label,
            original_yaml=raw_content,
            cleaned_yaml=cleaned_yaml,
            fields_removed=removed_fields,
            diff=diff_text,
            engine_used=engine_used,
            execution=execution,
            validation_passed=validation_passed,
            written=written,
            output_path=out_str,
        )
