"""Docker and container build error signatures."""

from typing import List
from devworkbench.signatures.base import BaseSignature


def get_docker_signatures() -> List[BaseSignature]:
    return [
        BaseSignature(
            signature_id="DOCKER-001",
            source="docker",
            category="build-step",
            patterns=[
                r"The command '(.*?)' returned a non-zero code:\s*(\d+)",
                r"executor failed running \[(.*?)\]:\s*exit code:\s*(\d+)",
            ],
            message_template="Docker build RUN command failed with exit code: {1}",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="DOCKER-002",
            source="docker",
            category="file-not-found",
            patterns=[
                r"failed to calculate checksum of ref .*?: \"(.*?)\": not found",
                r"COPY failed:\s*file not found",
            ],
            message_template="Docker build context missing required COPY file: {0}",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
