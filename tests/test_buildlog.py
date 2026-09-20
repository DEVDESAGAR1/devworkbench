"""Unit tests for the BuildLogAnalyzer and error signatures."""

import io
from pathlib import Path

from devworkbench.buildlog import BuildLogAnalyzer


def test_registry_auth_failure_with_cascading_events(tmp_path: Path) -> None:
    log_file = tmp_path / "build.log"
    log_file.write_text("""[Pipeline] stage: Build Image
Building Docker image...
Pushing image to registry.internal.corp:5000/app:1.0.0
Error: unauthorized: authentication required
The push refers to repository [registry.internal.corp:5000/app]
ERROR: script returned exit code 1
[Pipeline] } // stage
[Pipeline] } // node
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
""")

    analyzer = BuildLogAnalyzer()
    report = analyzer.analyze_file(str(log_file))

    assert report.total_lines > 0
    assert len(report.root_causes) >= 1
    rc = report.root_causes[0]
    assert "authentication failed" in rc.title.lower()
    assert rc.confidence == "Likely root cause"
    assert rc.source == "registry"
    assert len(rc.related_failures) >= 1


def test_kubernetes_crashloop_and_imagepullbackoff(tmp_path: Path) -> None:
    log_file = tmp_path / "k8s_deploy.log"
    log_file.write_text("""deployment.apps/payment-api created
Waiting for deployment "payment-api" rollout to finish...
pod/payment-api-6b797f6685-abcde: Container payment-api is in CrashLoopBackOff
pod/payment-api-6b797f6685-abcde: Back-off restarting failed container
pod/payment-api-6b797f6685-fghij: ImagePullBackOff
error: deployment "payment-api" exceeded its progress deadline
""")

    analyzer = BuildLogAnalyzer()
    report = analyzer.analyze_file(str(log_file))

    assert len(report.root_causes) >= 2
    sources = {rc.source for rc in report.root_causes}
    assert "kubernetes" in sources


def test_openshift_scc_failure(tmp_path: Path) -> None:
    log_file = tmp_path / "ocp.log"
    log_file.write_text("""Applying OpenShift resources...
Error from server (Forbidden): pods "frontend-1-abc" is forbidden: unable to validate against any security context constraint: [provider "restricted": ...]
Deployment failed.
""")

    analyzer = BuildLogAnalyzer()
    report = analyzer.analyze_file(str(log_file))

    assert len(report.root_causes) >= 1
    rc = report.root_causes[0]
    assert rc.source == "openshift"
    assert "SecurityContextConstraints" in rc.title


def test_helm_template_rendering_failure(tmp_path: Path) -> None:
    log_file = tmp_path / "helm.log"
    log_file.write_text("""[Pipeline] sh
+ helm upgrade --install payment-svc ./chart
Error: execution error at (payment-svc/templates/deployment.yaml:12:14): nil pointer evaluating interface .Values.image.tag
ERROR: script returned exit code 1
""")

    analyzer = BuildLogAnalyzer()
    report = analyzer.analyze_file(str(log_file))

    assert len(report.root_causes) >= 1
    rc = report.root_causes[0]
    assert rc.source == "helm"
    assert "template rendering" in rc.title.lower()


def test_repeated_error_deduplication(tmp_path: Path) -> None:
    log_file = tmp_path / "repeated.log"
    log_file.write_text("""Line 1: CrashLoopBackOff
Line 2: CrashLoopBackOff
Line 3: CrashLoopBackOff
Line 4: CrashLoopBackOff
""")

    analyzer = BuildLogAnalyzer()
    report = analyzer.analyze_file(str(log_file))

    # Should group the 4 identical errors into 1 diagnostic entry
    assert len(report.diagnostics) == 1
    assert "(occurred 4 times)" in report.diagnostics[0].message


def test_stdin_stream_analysis() -> None:
    log_content = "unauthorized: authentication required\nERROR: script returned exit code 1\n"
    stream = io.StringIO(log_content)

    analyzer = BuildLogAnalyzer()
    report = analyzer.analyze_stream(stream, source_name="stdin")

    assert report.total_lines == 2
    assert len(report.root_causes) >= 1
    assert report.source_path == "stdin"
