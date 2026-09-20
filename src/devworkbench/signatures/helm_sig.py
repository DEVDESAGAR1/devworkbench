"""Helm deployment and template error signatures."""


from devworkbench.signatures.base import BaseSignature


def get_helm_signatures() -> list[BaseSignature]:
    return [
        BaseSignature(
            signature_id="HELM-001",
            source="helm",
            category="template-rendering",
            patterns=[
                r"execution error at \((.*?)\):\s*(.*)",
                r"error calling (include|template|default):\s*(.*)",
                r"nil pointer evaluating interface \.[a-zA-Z0-9_]+",
            ],
            message_template="Helm template rendering execution error: {1}",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="HELM-002",
            source="helm",
            category="release-state",
            patterns=[
                r"cannot re-use a name that is still in use",
                r"another operation \(install/upgrade/rollback\) is in progress",
                r"release: \"(.*?)\" not found",
            ],
            message_template="Helm release state error: {0}",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
