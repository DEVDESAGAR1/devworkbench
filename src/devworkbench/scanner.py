"""Safe, recursive workspace directory scanner and analysis orchestrator for DevWorkBench."""

import fnmatch
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from devworkbench.adapters.registry import AdapterRegistry
from devworkbench.configuration import ScanConfig
from devworkbench.correlation import CorrelationEngine
from devworkbench.deduplication import DiagnosticDeduplicator
from devworkbench.detector import DetectionEngine
from devworkbench.fixes import FixEngine
from devworkbench.models import (
    Diagnostic,
    DiagnosticSeverity,
    FileDetection,
    FixPlan,
    FixReport,
    FixSummary,
    HelmChart,
    ScanError,
    ScanResult,
    ScanSummary,
    Technology,
    ToolWarning,
)
from devworkbench.planner import FixPlanner
from devworkbench.rules.registry import RuleRegistry


class Scanner:
    """Recursively scans workspaces, discovers Helm projects, and analyzes DevOps/developer files."""

    def __init__(self, config: Optional[ScanConfig] = None) -> None:
        self.config = config or ScanConfig()
        self.adapter_registry = AdapterRegistry()
        self.rule_registry = RuleRegistry()

    def _should_ignore_dir(self, dir_name: str, rel_path: Path) -> bool:
        """Check whether a directory should be skipped."""
        if dir_name in self.config.ignored_dirs or dir_name.endswith(".egg-info"):
            return True
        rel_str = str(rel_path).replace("\\", "/")
        for pattern in self.config.ignored_dirs:
            if "*" in pattern and fnmatch.fnmatch(dir_name, pattern):
                return True
        for pattern in self.config.custom_ignore_patterns:
            if fnmatch.fnmatch(dir_name, pattern) or fnmatch.fnmatch(rel_str, pattern):
                return True
        return False

    def _should_ignore_file(self, file_name: str, rel_path: Path) -> bool:
        """Check whether an individual file should be skipped."""
        if file_name in self.config.ignored_files:
            return True
        rel_str = str(rel_path).replace("\\", "/")
        for pattern in self.config.custom_ignore_patterns:
            if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(rel_str, pattern):
                return True
        return False

    def _find_helm_chart_roots(self, base_path: Path) -> Dict[Path, str]:
        """Pre-scan to discover all Helm chart root directories in the workspace."""
        helm_roots: Dict[Path, str] = {}
        try:
            for root, dirs, files in os.walk(base_path, followlinks=self.config.follow_symlinks):
                root_path = Path(root)
                try:
                    rel_path = root_path.relative_to(base_path)
                except ValueError:
                    rel_path = root_path

                dirs[:] = [
                    d for d in dirs
                    if not self._should_ignore_dir(d, rel_path / d)
                ]

                for f in files:
                    if f.lower() in ["chart.yaml", "chart.yml"]:
                        chart_name = root_path.name
                        helm_roots[root_path.resolve()] = chart_name
                        break
        except Exception:
            pass
        return helm_roots

    def scan_path(
        self,
        target_path: Path,
        base_context_path: Optional[Path] = None,
    ) -> Tuple[List[FileDetection], List[HelmChart], List[Diagnostic], List[FileDetection], List[ScanError]]:
        """Scan a single path (either a single file or a directory)."""
        base_ctx = base_context_path or (target_path.parent if target_path.is_file() else target_path)
        base_ctx_resolved = base_ctx.resolve()
        target_path_resolved = target_path.resolve()

        detections: List[FileDetection] = []
        unknown_files: List[FileDetection] = []
        errors: List[ScanError] = []
        diagnostics: List[Diagnostic] = []
        helm_charts_map: Dict[Path, HelmChart] = {}

        # 1. Target is a single file
        if target_path_resolved.is_file():
            try:
                rel_path = target_path_resolved.relative_to(base_ctx_resolved)
            except ValueError:
                rel_path = Path(target_path.name)

            detection = DetectionEngine.detect_file(
                target_path_resolved,
                rel_path,
                max_bytes=self.config.max_inspection_bytes,
            )
            if detection.technology == Technology.UNKNOWN:
                unknown_files.append(detection)
            else:
                detections.append(detection)

                # Adapters analysis
                adapters = self.adapter_registry.get_adapters_for_file(detection)
                for adapter in adapters:
                    if adapter.name.lower() in self.config.disabled_engines:
                        continue
                    try:
                        diags = adapter.analyze_file(target_path_resolved, detection)
                        diagnostics.extend(diags)
                    except Exception as e:
                        errors.append(
                            ScanError(
                                path=str(target_path_resolved),
                                relative_path=str(rel_path),
                                error_message=f"Analysis error in {adapter.name}: {e}",
                            )
                        )

                # Best practice rules
                rule_diags = self.rule_registry.evaluate_rules(
                    file_path=target_path_resolved,
                    detection=detection,
                )
                diagnostics.extend(rule_diags)

            return detections, list(helm_charts_map.values()), diagnostics, unknown_files, errors

        # 2. Target is a directory
        helm_roots = self._find_helm_chart_roots(target_path_resolved)
        for root_p, name in helm_roots.items():
            try:
                rel_root = str(root_p.relative_to(base_ctx_resolved)).replace("\\", "/")
            except ValueError:
                rel_root = str(root_p).replace("\\", "/")
            helm_charts_map[root_p] = HelmChart(
                name=name,
                root_path=str(root_p),
                relative_root=rel_root if rel_root != "." else root_p.name,
            )

        visited_inodes: Set[Tuple[int, int]] = set()

        for root, dirs, files in os.walk(target_path_resolved, followlinks=self.config.follow_symlinks):
            root_path = Path(root)
            try:
                rel_dir = root_path.relative_to(base_ctx_resolved)
            except ValueError:
                rel_dir = root_path

            try:
                stat_info = root_path.stat()
                inode_key = (stat_info.st_dev, stat_info.st_ino)
                if inode_key in visited_inodes:
                    dirs.clear()
                    continue
                visited_inodes.add(inode_key)
            except Exception:
                pass

            dirs[:] = [
                d for d in dirs
                if not self._should_ignore_dir(d, rel_dir / d)
            ]

            current_helm_root: Optional[Path] = None
            for hr in helm_roots:
                if root_path == hr or hr in root_path.parents:
                    current_helm_root = hr
                    break

            for file_name in files:
                file_path = root_path / file_name
                try:
                    rel_file_path = file_path.relative_to(base_ctx_resolved)
                except ValueError:
                    rel_file_path = Path(file_name)

                if self._should_ignore_file(file_name, rel_file_path):
                    continue

                try:
                    is_helm_chart = current_helm_root is not None
                    is_helm_template = False
                    if current_helm_root is not None:
                        try:
                            rel_to_chart = file_path.relative_to(current_helm_root)
                            if "templates" in [p.lower() for p in rel_to_chart.parts]:
                                is_helm_template = True
                        except ValueError:
                            pass

                    detection = DetectionEngine.detect_file(
                        file_path=file_path,
                        relative_path=rel_file_path,
                        is_helm_template=is_helm_template,
                        is_helm_chart=is_helm_chart,
                        max_bytes=self.config.max_inspection_bytes,
                    )

                    if current_helm_root and current_helm_root in helm_charts_map:
                        hc = helm_charts_map[current_helm_root]
                        rel_in_chart = str(file_path.relative_to(current_helm_root)).replace("\\", "/")
                        fname_l = file_name.lower()
                        if fname_l in ["chart.yaml", "chart.yml"]:
                            hc.chart_yaml = rel_in_chart
                        elif fname_l.startswith("values"):
                            hc.values_files.append(rel_in_chart)
                        elif is_helm_template:
                            if fname_l.endswith(".tpl"):
                                hc.helper_files.append(rel_in_chart)
                            else:
                                hc.template_files.append(rel_in_chart)
                        elif "charts" in [p.lower() for p in file_path.relative_to(current_helm_root).parts]:
                            hc.subchart_files.append(rel_in_chart)
                        else:
                            hc.other_files.append(rel_in_chart)

                    if detection.technology == Technology.UNKNOWN:
                        unknown_files.append(detection)
                    else:
                        detections.append(detection)

                        # Run file-level adapter analysis
                        adapters = self.adapter_registry.get_adapters_for_file(detection)
                        for adapter in adapters:
                            if adapter.name.lower() in self.config.disabled_engines:
                                continue
                            try:
                                diags = adapter.analyze_file(file_path, detection)
                                diagnostics.extend(diags)
                            except Exception as e:
                                errors.append(
                                    ScanError(
                                        path=str(file_path),
                                        relative_path=str(rel_file_path),
                                        error_message=f"Analysis error in {adapter.name}: {e}",
                                    )
                                )

                        # Run best-practice rules
                        rule_diags = self.rule_registry.evaluate_rules(
                            file_path=file_path,
                            detection=detection,
                        )
                        diagnostics.extend(rule_diags)

                except (PermissionError, OSError) as e:
                    errors.append(
                        ScanError(
                            path=str(file_path),
                            relative_path=str(rel_file_path),
                            error_message=str(e),
                        )
                    )
                except Exception as e:
                    errors.append(
                        ScanError(
                            path=str(file_path),
                            relative_path=str(rel_file_path),
                            error_message=f"Unexpected error: {str(e)}",
                        )
                    )

        # Helm project-level checks
        helm_adapter = self.adapter_registry.get_adapter_for_tech(Technology.HELM)
        if helm_adapter and helm_adapter.name.lower() not in self.config.disabled_engines:
            for hc in helm_charts_map.values():
                try:
                    diags = helm_adapter.analyze_project(Path(hc.root_path), chart=hc)
                    diagnostics.extend(diags)
                except Exception as e:
                    errors.append(
                        ScanError(
                            path=hc.root_path,
                            relative_path=hc.relative_root,
                            error_message=f"Helm project analysis error: {e}",
                        )
                    )

        return detections, list(helm_charts_map.values()), diagnostics, unknown_files, errors

    def scan_multiple(self, target_paths: List[str]) -> ScanResult:
        """Scan multiple files and/or directories."""
        start_time = time.perf_counter()

        if not target_paths:
            target_paths = ["."]

        all_detections: List[FileDetection] = []
        all_helm_charts: List[HelmChart] = []
        all_diagnostics: List[Diagnostic] = []
        all_unknown_files: List[FileDetection] = []
        all_errors: List[ScanError] = []

        seen_paths: Set[str] = set()

        for p_str in target_paths:
            path_obj = Path(p_str)
            if not path_obj.exists():
                raise FileNotFoundError(f"Target path does not exist: {p_str}")

            dets, charts, diags, unks, errs = self.scan_path(path_obj)

            for d in dets:
                if d.path not in seen_paths:
                    seen_paths.add(d.path)
                    all_detections.append(d)

            all_helm_charts.extend(charts)
            all_diagnostics.extend(diags)
            all_unknown_files.extend(unks)
            all_errors.extend(errs)

        # 1. Deduplicate diagnostics across engines
        deduplicated_diags = DiagnosticDeduplicator.deduplicate(all_diagnostics)

        # 2. Filter out disabled rules and apply severity overrides
        final_diagnostics: List[Diagnostic] = []
        for d in deduplicated_diags:
            if d.rule and d.rule in self.config.disabled_rules:
                continue
            if d.rule and d.rule in self.config.severity_overrides:
                d.severity = self.config.severity_overrides[d.rule]
            final_diagnostics.append(d)

        # 3. Collect tool warnings
        active_technologies = {d.technology for d in all_detections}
        tool_warnings = self.adapter_registry.get_tool_warnings(active_technologies)

        # 4. Run correlation engine
        correlations = CorrelationEngine.correlate(
            detections=all_detections,
            diagnostics=final_diagnostics,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        total_discovered = len(all_detections) + len(all_unknown_files) + len(all_errors)
        errors_count = sum(1 for d in final_diagnostics if d.severity == DiagnosticSeverity.ERROR)
        warnings_count = sum(1 for d in final_diagnostics if d.severity == DiagnosticSeverity.WARNING)
        files_with_issues = len(
            {d.path for d in final_diagnostics if d.severity in [DiagnosticSeverity.ERROR, DiagnosticSeverity.WARNING]}
        )

        summary = ScanSummary(
            total_files_discovered=total_discovered,
            supported_files=len(all_detections),
            unknown_files=len(all_unknown_files),
            error_files=len(all_errors),
            helm_charts_count=len(all_helm_charts),
            analyzed_files=len(all_detections),
            errors_count=errors_count,
            warnings_count=warnings_count,
            files_with_issues=files_with_issues,
            tools_unavailable_count=len(tool_warnings),
            root_causes_count=len(correlations),
            duration_ms=round(duration_ms, 2),
            modified_files=0,  # Strict immutability
        )

        display_path = ", ".join(target_paths) if len(target_paths) > 1 else target_paths[0]

        return ScanResult(
            target_path=display_path,
            detections=all_detections,
            helm_charts=all_helm_charts,
            diagnostics=final_diagnostics,
            correlations=correlations,
            tool_warnings=tool_warnings,
            unknown_files=all_unknown_files,
            errors=all_errors,
            summary=summary,
        )

    def scan(self, target_path_str: str) -> ScanResult:
        """Scan a single target path."""
        return self.scan_multiple([target_path_str])

    def plan_fix(self, target_paths: List[str]) -> Tuple[ScanResult, FixPlan]:
        """Perform initial scan and build fix plan."""
        scan_res = self.scan_multiple(target_paths)
        plan = FixPlanner.create_plan(
            diagnostics=scan_res.diagnostics,
            target_paths=target_paths,
        )
        return scan_res, plan

    def run_fix(
        self,
        target_paths: List[str],
        plan: Optional[FixPlan] = None,
        dry_run: bool = False,
        confirmed: bool = True,
    ) -> FixReport:
        """Execute fix workflow with planning, integrity protection, and post-fix validation."""
        start_time = time.perf_counter()

        initial_scan = self.scan_multiple(target_paths)
        if plan is None:
            plan = FixPlanner.create_plan(
                diagnostics=initial_scan.diagnostics,
                target_paths=target_paths,
            )

        before_errors = initial_scan.summary.errors_count
        before_warnings = initial_scan.summary.warnings_count
        total_candidates = len(plan.safe_candidates) + len(plan.manual_candidates)

        if dry_run or not confirmed:
            duration_ms = (time.perf_counter() - start_time) * 1000
            summary = FixSummary(
                files_analyzed=initial_scan.summary.analyzed_files,
                fix_candidates=total_candidates,
                applied_count=0,
                skipped_count=0,
                failed_count=0,
                resolved_count=0,
                remaining_count=len(initial_scan.diagnostics),
                files_modified=0,
                before_errors=before_errors,
                before_warnings=before_warnings,
                after_errors=before_errors,
                after_warnings=before_warnings,
                duration_ms=round(duration_ms, 2),
            )
            return FixReport(
                target_paths=target_paths,
                plan=plan,
                summary=summary,
                results=[],
                remaining_diagnostics=initial_scan.diagnostics,
                resolved_diagnostics=[],
                engine_states={},
                confirmed=False if dry_run else confirmed,
            )

        # Apply safe fixes
        results, engine_states, files_modified = FixEngine.execute_plan(
            plan=plan,
            adapter_registry=self.adapter_registry,
        )

        # Post-Fix Validation Scan
        post_scan = self.scan_multiple(target_paths)

        before_keys = {(d.path, d.line, d.rule, d.message) for d in initial_scan.diagnostics}
        after_keys = {(d.path, d.line, d.rule, d.message) for d in post_scan.diagnostics}

        resolved_diagnostics = [d for d in initial_scan.diagnostics if (d.path, d.line, d.rule, d.message) not in after_keys]
        remaining_diagnostics = post_scan.diagnostics

        applied_count = sum(1 for r in results if r.status == "applied")
        skipped_count = sum(1 for r in results if r.status == "skipped")
        failed_count = sum(1 for r in results if r.status == "failed")
        duration_ms = (time.perf_counter() - start_time) * 1000

        summary = FixSummary(
            files_analyzed=initial_scan.summary.analyzed_files,
            fix_candidates=total_candidates,
            applied_count=applied_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            resolved_count=len(resolved_diagnostics),
            remaining_count=len(remaining_diagnostics),
            files_modified=files_modified,
            before_errors=before_errors,
            before_warnings=before_warnings,
            after_errors=post_scan.summary.errors_count,
            after_warnings=post_scan.summary.warnings_count,
            duration_ms=round(duration_ms, 2),
        )

        return FixReport(
            target_paths=target_paths,
            plan=plan,
            summary=summary,
            results=results,
            resolved_diagnostics=resolved_diagnostics,
            remaining_diagnostics=remaining_diagnostics,
            engine_states=engine_states,
            confirmed=True,
        )

