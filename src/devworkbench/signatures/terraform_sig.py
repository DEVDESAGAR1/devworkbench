"""Terraform runtime error signatures."""

from typing import List
from devworkbench.signatures.base import BaseSignature


def get_terraform_signatures() -> List[BaseSignature]:
    return [
        BaseSignature(
            signature_id="TF-001",
            source="terraform",
            category="state-lock",
            patterns=[
                r"Error:\s*Error acquiring the state lock",
                r"Lock Info:\s*ID:\s*(.*)",
            ],
            message_template="Terraform state lock is held by another process or crashed run",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="TF-002",
            source="terraform",
            category="provider-init",
            patterns=[
                r"Failed to query available provider packages",
                r"Could not retrieve the list of available versions for provider",
            ],
            message_template="Terraform provider initialization or download failed",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
