"""Runner and execution orchestrator for DevWorkBench."""

from typing import Any, List, Optional

from devworkbench.buildlog import BuildLogAnalyzer
from devworkbench.configuration import ScanConfig
from devworkbench.models import BuildLogReport, FixPlan, FixReport, ScanResult
from devworkbench.reporter import HumanReporter, JsonReporter
from devworkbench.scanner import Scanner


class Runner:
    """Orchestrates scan execution, build log analysis, fix execution, and reporting pipelines."""

    def __init__(self, config: Optional[ScanConfig] = None) -> None:
        self.config = config or ScanConfig()
        self.scanner = Scanner(config=self.config)
        self.build_analyzer = BuildLogAnalyzer()

    def run_scan(
        self,
        target_paths: List[str],
        output_format: str = "human",
        output_file: Optional[str] = None,
        verbose: bool = False,
    ) -> ScanResult:
        """Run scan across one or more target paths and emit reports."""
        result = self.scanner.scan_multiple(target_paths)

        if output_format.lower() == "json":
            json_str = JsonReporter.format(result)
            if output_file:
                JsonReporter.write_to_file(result, output_file)
            else:
                print(json_str)
        else:
            human_reporter = HumanReporter()
            human_reporter.report(result, verbose=verbose)
            if output_file:
                JsonReporter.write_to_file(result, output_file)

        return result

    def run_fix(
        self,
        target_paths: List[str],
        plan: Optional[FixPlan] = None,
        dry_run: bool = False,
        confirmed: bool = True,
        output_format: str = "human",
        output_file: Optional[str] = None,
    ) -> FixReport:
        """Run fix pipeline (dry run or confirmed execution) and emit reports."""
        report = self.scanner.run_fix(
            target_paths=target_paths,
            plan=plan,
            dry_run=dry_run,
            confirmed=confirmed,
        )

        if output_format.lower() == "json":
            json_str = JsonReporter.format(report)
            if output_file:
                JsonReporter.write_to_file(report, output_file)
            else:
                print(json_str)
        else:
            human_reporter = HumanReporter()
            if dry_run or not confirmed:
                human_reporter.report_fix_plan(report.plan, dry_run=dry_run)
            else:
                human_reporter.report_fix_results(report)
            if output_file:
                JsonReporter.write_to_file(report, output_file)

        return report

    def run_analyze_build(
        self,
        log_path: str,
        output_format: str = "human",
        output_file: Optional[str] = None,
        stream: Optional[Any] = None,
    ) -> BuildLogReport:
        """Analyze a build log file or stream."""
        if stream is not None:
            report = self.build_analyzer.analyze_stream(stream, source_name="stdin")
        else:
            report = self.build_analyzer.analyze_file(log_path)

        if output_format.lower() == "json":
            json_str = JsonReporter.format(report)
            if output_file:
                JsonReporter.write_to_file(report, output_file)
            else:
                print(json_str)
        else:
            human_reporter = HumanReporter()
            human_reporter.report_build_log(report)
            if output_file:
                JsonReporter.write_to_file(report, output_file)

        return report
