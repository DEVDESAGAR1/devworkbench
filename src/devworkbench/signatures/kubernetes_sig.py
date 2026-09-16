"""Kubernetes runtime error signatures."""

from typing import List
from devworkbench.signatures.base import BaseSignature


def get_kubernetes_signatures() -> List[BaseSignature]:
    return [
        BaseSignature(
            signature_id="K8S-001",
            source="kubernetes",
            category="pod-lifecycle",
            patterns=[
                r"\bCrashLoopBackOff\b",
                r"Back-off restarting failed container",
            ],
            message_template="Pod container is crashing repeatedly (CrashLoopBackOff)",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="K8S-002",
            source="kubernetes",
            category="image-pull",
            patterns=[
                r"\bImagePullBackOff\b",
                r"\bErrImagePull\b",
                r"Failed to pull image",
            ],
            message_template="Kubelet failed to pull container image (ImagePullBackOff / ErrImagePull)",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="K8S-003",
            source="kubernetes",
            category="resource-exhaustion",
            patterns=[
                r"\bOOMKilled\b",
                r"exit code 137",
                r"command terminated with exit code 137",
            ],
            message_template="Container was terminated due to memory limit exhaustion (OOMKilled)",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="K8S-004",
            source="kubernetes",
            category="admission",
            patterns=[
                r'admission webhook "(.*?)" denied the request:\s*(.*)',
                r'Error from server \(Forbidden\):\s*(.*)',
            ],
            message_template="Kubernetes admission controller or RBAC denied the request: {1}",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
