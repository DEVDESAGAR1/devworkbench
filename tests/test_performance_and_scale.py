"""Performance and scaling benchmark tests."""

import time
from pathlib import Path
from devworkbench.scanner import Scanner


def test_scale_repository_scan_100_files(tmp_path: Path):
    """Verify scanning 100+ mixed files runs smoothly and performs deduplication in reasonable time."""
    # Generate 120 files across python, yaml, shell, dockerfile, etc.
    for i in range(30):
        (tmp_path / f"script_{i}.py").write_text(f"x = {i}\nprint(x)\n")
    for i in range(30):
        (tmp_path / f"manifest_{i}.yaml").write_text(f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cm-{i}\n")
    for i in range(30):
        (tmp_path / f"deploy_{i}.sh").write_text(f"#!/bin/bash\necho 'Deploying {i}'\n")
    for i in range(15):
        (tmp_path / f"Dockerfile.{i}").write_text("FROM alpine:3.18\nRUN echo 'ok'\n")
    for i in range(15):
        (tmp_path / f"main_{i}.tf").write_text('variable "env" { default = "dev" }\n')

    start_time = time.perf_counter()
    scanner = Scanner()
    result = scanner.scan(tmp_path)
    elapsed = time.perf_counter() - start_time

    assert result.summary.total_files_discovered == 120
    # 120 mixed files scanning across all engines and deduplication
    assert elapsed < 30.0, f"Scan took {elapsed:.2f}s, expected < 30.0s"
