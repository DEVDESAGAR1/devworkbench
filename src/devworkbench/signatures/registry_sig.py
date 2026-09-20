"""Registry authentication and image storage signatures."""


from devworkbench.signatures.base import BaseSignature


def get_registry_signatures() -> list[BaseSignature]:
    return [
        BaseSignature(
            signature_id="REG-001",
            source="registry",
            category="authentication",
            patterns=[
                r"unauthorized:\s*authentication required",
                r"denied:\s*requested access to the resource is denied",
                r"failed to fetch anonymous token",
                r"no basic auth credentials",
                r"401 Unauthorized",
            ],
            message_template="Container registry authentication failed (401 / Denied)",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="REG-002",
            source="registry",
            category="image-not-found",
            patterns=[
                r"manifest unknown:\s*manifest unknown",
                r"manifest for .* not found",
                r"image .* not found",
                r"404 Not Found.*manifests",
            ],
            message_template="Requested container image manifest was not found in registry (404)",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
