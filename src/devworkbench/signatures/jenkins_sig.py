"""Jenkins pipeline runtime error signatures."""


from devworkbench.signatures.base import BaseSignature


def get_jenkins_signatures() -> list[BaseSignature]:
    return [
        BaseSignature(
            signature_id="JENK-001",
            source="jenkins",
            category="stage-failure",
            patterns=[
                r"ERROR:\s*script returned exit code\s*(\d+)",
                r"Failed in branch\s*(.*)",
                r"org\.jenkinsci\.plugins\.workflow\.steps\.FlowInterruptedException",
            ],
            message_template="Pipeline step failed with non-zero exit code: {0}",
            is_root_cause=False,  # Downstream cascaded symptom
            confidence="Possible root cause",
        ),
        BaseSignature(
            signature_id="JENK-002",
            source="jenkins",
            category="agent-connectivity",
            patterns=[
                r"hudson\.remoting\.ChannelClosedException",
                r"Agent went offline during the build",
                r"Cannot contact agent:\s*(.*)",
            ],
            message_template="Jenkins build agent disconnected or went offline during execution",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
        BaseSignature(
            signature_id="JENK-003",
            source="jenkins",
            category="credential-binding",
            patterns=[
                r"Could not find credentials matching\s*['\"](.*?)['\"]",
                r"Credentials '.*' not found",
            ],
            message_template="Jenkins credentials binding failure: Specified credentials ID not found",
            is_root_cause=True,
            confidence="Likely root cause",
        ),
    ]
