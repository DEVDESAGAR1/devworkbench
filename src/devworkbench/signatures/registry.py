"""Registry collecting all error signatures for build log analysis."""

from typing import List, Optional

from devworkbench.signatures.base import BaseSignature, SignatureMatch
from devworkbench.signatures.docker_sig import get_docker_signatures
from devworkbench.signatures.helm_sig import get_helm_signatures
from devworkbench.signatures.jenkins_sig import get_jenkins_signatures
from devworkbench.signatures.kubernetes_sig import get_kubernetes_signatures
from devworkbench.signatures.openshift_sig import get_openshift_signatures
from devworkbench.signatures.registry_sig import get_registry_signatures
from devworkbench.signatures.terraform_sig import get_terraform_signatures


class SignatureRegistry:
    """Central registry of all regex-based error signatures.

    Signatures are prioritized from most specific (Registry, OpenShift, Helm, Terraform)
    to broader/downstream runtime patterns (Kubernetes, Docker, Jenkins).
    """

    def __init__(self) -> None:
        self.signatures: List[BaseSignature] = []
        # Specific domain error signatures first
        self.signatures.extend(get_registry_signatures())
        self.signatures.extend(get_openshift_signatures())
        self.signatures.extend(get_helm_signatures())
        self.signatures.extend(get_terraform_signatures())
        self.signatures.extend(get_docker_signatures())
        self.signatures.extend(get_kubernetes_signatures())
        self.signatures.extend(get_jenkins_signatures())

    def match_line(self, line: str, line_number: int) -> Optional[SignatureMatch]:
        """Match line against all registered signatures."""
        for sig in self.signatures:
            match = sig.match_line(line, line_number)
            if match:
                return match
        return None
