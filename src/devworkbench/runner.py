"""Runner and execution orchestrator for DevWorkBench."""

from typing import Any

from devworkbench.buildlog import BuildLogAnalyzer
from devworkbench.configuration import ScanConfig
from devworkbench.models import BuildLogReport, FixPlan, FixReport, ScanResult
from devworkbench.reporter import HumanReporter, JsonReporter
from devworkbench.scanner import Scanner


class Runner:
    """Orchestrates scan execution, build log analysis, fix execution, and reporting pipelines."""

    def __init__(self, config: ScanConfig | None = None) -> None:
        self.config = config or ScanConfig()
        self.scanner = Scanner(config=self.config)
        self.build_analyzer = BuildLogAnalyzer()

    def run_scan(
        self,
        target_paths: list[str],
        output_format: str = "human",
        output_file: str | None = None,
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
        target_paths: list[str],
        plan: FixPlan | None = None,
        dry_run: bool = False,
        confirmed: bool = True,
        output_format: str = "human",
        output_file: str | None = None,
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
        output_file: str | None = None,
        stream: Any | None = None,
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

    def run_clean(
        self,
        target_path_or_content: str,
        write_output_path: str | None = None,
        output_format: str = "human",
        output_file: str | None = None,
    ) -> Any:
        """Clean Kubernetes manifest and output result in requested format."""
        from pathlib import Path

        from devworkbench.cleaner import ManifestCleaner

        out_path = Path(write_output_path) if write_output_path else None
        result = ManifestCleaner.clean(
            content_or_path=target_path_or_content,
            write_output_path=out_path,
        )

        if output_format.lower() == "json":
            json_str = JsonReporter.format(result)
            if output_file:
                JsonReporter.write_to_file(result, output_file)
            else:
                print(json_str)
        else:
            human_reporter = HumanReporter()
            human_reporter.report_cleanup_result(result, format_mode=output_format)
            if output_file:
                JsonReporter.write_to_file(result, output_file)

        return result

    def run_convert(
        self,
        input_paths: list[str],
        target_dir: str,
        chart_name: str | None = None,
        to_format: str = "helm",
        dry_run: bool = False,
        force: bool = False,
        output_format: str = "human",
        output_file: str | None = None,
    ) -> Any:
        """Convert Kubernetes manifests to Helm chart."""
        from pathlib import Path

        from devworkbench.converter import HelmConverter

        path_objs = [Path(p) for p in input_paths]
        target_dir_obj = Path(target_dir)

        result = HelmConverter.convert(
            input_paths=path_objs,
            target_dir=target_dir_obj,
            chart_name=chart_name,
            dry_run=dry_run,
            force=force,
        )

        if output_format.lower() == "json":
            json_str = JsonReporter.format(result)
            if output_file:
                JsonReporter.write_to_file(result, output_file)
            else:
                print(json_str)
        else:
            human_reporter = HumanReporter()
            if dry_run:
                human_reporter.report_conversion_plan(result.plan)
            else:
                human_reporter.report_conversion_results(result)
            if output_file:
                JsonReporter.write_to_file(result, output_file)

        return result

    def run_migrate(
        self,
        input_dir: str | None = None,
        to_format: str = "helm",
        reference: str | None = None,
        example_name: str | None = None,
        output_dir: str | None = None,
        chart_name: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        output_format: str = "human",
        output_file: str | None = None,
        auto_confirm: bool = False,
        provider_preference: str = "auto",
    ) -> Any:
        """Execute reference-aware Kubernetes to Helm migration."""
        import sys
        from pathlib import Path

        from devworkbench.migration.detector import ManifestDetector
        from devworkbench.migration.examples import ExampleRegistry
        from devworkbench.migration.generator import HelmGenerator

        human_reporter = HumanReporter()

        # 1. Discover resources from directory or CWD
        if input_dir:
            input_path = Path(input_dir)
            if not input_path.exists():
                raise FileNotFoundError(f"Input path does not exist: {input_path}")
            if input_path.is_file():
                resources = ManifestDetector._parse_file(input_path, base_dir=input_path.parent)
            else:
                resources = ManifestDetector.discover_directory(input_path)
        else:
            workspace_info = ManifestDetector.inspect_workspace(Path.cwd())
            resources = workspace_info.get("resources", [])
            if not resources:
                raise ValueError("No Kubernetes manifests discovered in current directory.")

            if output_format.lower() != "json" and not auto_confirm and sys.stdin.isatty():
                human_reporter.report_workspace_candidates(workspace_info)
                response = input("Use discovered Kubernetes manifests as migration input? [Y/n]: ").strip().lower()
                if response in ("n", "no"):
                    return None

        if not resources:
            raise ValueError("No valid Kubernetes resources found to migrate.")

        # 2. Resolve reference pattern if requested
        ref_pattern = None
        if example_name:
            registry = ExampleRegistry()
            ref_pattern = registry.get_example(example_name)
        elif reference:
            if reference.lower() == "auto":
                # Discover possible Helm charts in workspace
                workspace_info = ManifestDetector.inspect_workspace(Path.cwd())
                candidate_charts = workspace_info.get("helm_charts", [])
                if len(candidate_charts) == 1:
                    ref_pattern = ExampleRegistry.analyze_chart(Path(candidate_charts[0]))
                elif len(candidate_charts) > 1 and output_format.lower() != "json" and not auto_confirm and sys.stdin.isatty():
                    human_reporter.console.print("[bold yellow]Multiple Helm references discovered:[/bold yellow]")
                    for idx, c in enumerate(candidate_charts, 1):
                        human_reporter.console.print(f"  {idx}. {c}")
                    choice = input(f"Select reference [1-{len(candidate_charts)}]: ").strip()
                    try:
                        c_idx = int(choice) - 1
                        ref_pattern = ExampleRegistry.analyze_chart(Path(candidate_charts[c_idx]))
                    except Exception:
                        ref_pattern = None
            else:
                ref_path = Path(reference)
                ref_pattern = ExampleRegistry.analyze_chart(ref_path)

        # 3. Determine target directory
        effective_output_dir = Path(output_dir) if output_dir else Path.cwd() / (chart_name or "generated-chart")

        # 4. Generate Helm chart
        result = HelmGenerator.generate(
            resources=resources,
            target_dir=effective_output_dir,
            chart_name=chart_name,
            reference=ref_pattern,
            provider_preference=provider_preference,
            dry_run=dry_run,
            force=force,
        )

        # 5. Report results
        if output_format.lower() == "json":
            json_str = JsonReporter.format(result)
            if output_file:
                JsonReporter.write_to_file(result, output_file)
            else:
                print(json_str)
        else:
            if dry_run:
                human_reporter.report_migration_plan(result.plan)
            else:
                human_reporter.report_migration_results(result)
            if output_file:
                JsonReporter.write_to_file(result, output_file)

        return result

    def run_examples_add(
        self,
        chart_dir: str,
        name: str | None = None,
        output_format: str = "human",
    ) -> Any:
        """Add a Helm chart as a named reference example."""
        from pathlib import Path

        from devworkbench.migration.examples import ExampleRegistry

        registry = ExampleRegistry()
        pattern = registry.add_example(Path(chart_dir), name=name)

        if output_format.lower() == "json":
            print(JsonReporter.format(pattern))
        else:
            human_reporter = HumanReporter()
            human_reporter.console.print(f"[bold green]Successfully ingested reference example:[/bold green] [bold cyan]{pattern.name}[/bold cyan]")
            human_reporter.report_example_details(pattern)
        return pattern

    def run_examples_list(self, output_format: str = "human") -> list[dict[str, Any]]:
        """List all ingested reference examples."""
        from devworkbench.migration.examples import ExampleRegistry

        registry = ExampleRegistry()
        examples = registry.list_examples()

        if output_format.lower() == "json":
            print(JsonReporter.format(examples))
        else:
            human_reporter = HumanReporter()
            human_reporter.report_examples_list(examples)
        return examples

    def run_examples_inspect(self, name: str, output_format: str = "human") -> Any:
        """Inspect a specific ingested reference example."""
        from devworkbench.migration.examples import ExampleRegistry

        registry = ExampleRegistry()
        pattern = registry.get_example(name)

        if output_format.lower() == "json":
            print(JsonReporter.format(pattern))
        else:
            human_reporter = HumanReporter()
            human_reporter.report_example_details(pattern)
        return pattern

    def run_examples_remove(self, name: str, output_format: str = "human") -> bool:
        """Remove a reference example from local storage."""
        from devworkbench.migration.examples import ExampleRegistry

        registry = ExampleRegistry()
        removed = registry.remove_example(name)

        if output_format.lower() == "json":
            print(JsonReporter.format({"name": name, "removed": removed}))
        else:
            human_reporter = HumanReporter()
            if removed:
                human_reporter.console.print(f"[bold green]Removed reference example:[/bold green] [cyan]{name}[/cyan]")
            else:
                human_reporter.console.print(f"[bold yellow]Reference example not found:[/bold yellow] [dim]{name}[/dim]")
        return removed

    def run_helm_inspect(self, chart_dir: str, output_format: str = "human") -> Any:
        """Inspect any Helm chart directory without persisting to storage."""
        from pathlib import Path

        from devworkbench.migration.examples import ExampleRegistry

        pattern = ExampleRegistry.analyze_chart(Path(chart_dir))

        if output_format.lower() == "json":
            print(JsonReporter.format(pattern))
        else:
            human_reporter = HumanReporter()
            human_reporter.report_example_details(pattern)
        return pattern

