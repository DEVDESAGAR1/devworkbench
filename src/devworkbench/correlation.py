"""Cross-tool correlation engine linking static pipeline definitions with runtime diagnostics."""

from typing import List, Optional

from devworkbench.models import (
    Correlation,
    Diagnostic,
    FileDetection,
    RootCauseCandidate,
    Technology,
)


class CorrelationEngine:
    """Deterministic correlation engine for cross-tool DevOps diagnostics."""

    @classmethod
    def correlate(
        cls,
        detections: List[FileDetection],
        diagnostics: List[Diagnostic],
        root_causes: Optional[List[RootCauseCandidate]] = None,
    ) -> List[Correlation]:
        """Correlate static detections and runtime diagnostics into structured correlation chains."""
        correlations: List[Correlation] = []
        root_causes = root_causes or []

        # 1. Check for Jenkins -> Helm -> Kubernetes chain
        jenkins_files = [d for d in detections if d.technology == Technology.JENKINS]
        helm_files = [d for d in detections if d.technology == Technology.HELM]
        k8s_files = [d for d in detections if d.technology == Technology.KUBERNETES]

        for jf in jenkins_files:
            invoked_tools = jf.metadata.get("invoked_tools", [])

            # Jenkins -> Helm
            if "helm" in invoked_tools and helm_files:
                helm_diags = [d for d in diagnostics if "helm" in d.source.lower()]
                matched_rc = next((rc for rc in root_causes if rc.source == "helm"), None)
                if helm_diags or matched_rc:
                    correlations.append(
                        Correlation(
                            id="CORR-JENK-HELM",
                            technology_chain=["Jenkins", "Helm", "Kubernetes"],
                            root_cause_candidate=matched_rc,
                            confidence=0.85,
                            explanation=f"Jenkinsfile '{jf.relative_path}' invokes Helm which encountered template/release errors.",
                            diagnostics=helm_diags,
                        )
                    )

            # Jenkins -> OpenShift (oc)
            if "oc" in invoked_tools:
                ocp_diags = [d for d in diagnostics if "openshift" in d.source.lower() or "ocp" in (d.rule or "").lower()]
                matched_rc = next((rc for rc in root_causes if rc.source == "openshift"), None)
                if ocp_diags or matched_rc:
                    correlations.append(
                        Correlation(
                            id="CORR-JENK-OCP",
                            technology_chain=["Jenkins", "OpenShift", "SCC"],
                            root_cause_candidate=matched_rc,
                            confidence=0.90,
                            explanation=f"Jenkinsfile '{jf.relative_path}' executes OpenShift 'oc' commands with SCC or route issues.",
                            diagnostics=ocp_diags,
                        )
                    )

            # Jenkins -> Docker / Kaniko -> Registry
            if "docker" in invoked_tools or "podman" in invoked_tools:
                reg_rc = next((rc for rc in root_causes if rc.source == "registry"), None)
                if reg_rc:
                    correlations.append(
                        Correlation(
                            id="CORR-JENK-REGISTRY",
                            technology_chain=["Jenkins", "Container Build", "Registry"],
                            root_cause_candidate=reg_rc,
                            confidence=0.95,
                            explanation=f"Jenkinsfile '{jf.relative_path}' executes container operations that failed at the remote registry.",
                            diagnostics=[d for d in diagnostics if d.source == "registry"],
                        )
                    )

        return correlations
