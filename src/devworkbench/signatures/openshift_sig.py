"""OpenShift runtime error signatures."""


from devworkbench.signatures.base import BaseSignature


def get_openshift_signatures() -> list[BaseSignature]:
    return [
        BaseSignature(
            signature_id="OCP-001",
            source="openshift",
            category="scc",
            patterns=[
                r"unable to validate against any security context constraint",
                r"forbidden:\s*not validate against any security context constraint",
                r"does not have minimum permissions for pod security",
            ],
            message_template="OpenShift SecurityContextConstraints (SCC) violation: Pod cannot run with requested UID/GID or capabilities",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="OCP-002",
            source="openshift",
            category="routes",
            patterns=[
                r"Route \"(.*?)\" is invalid:\s*(.*)",
                r"HostAlreadyClaimed",
                r"Route admission failed",
            ],
            message_template="OpenShift Route admission conflict or invalid host",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
