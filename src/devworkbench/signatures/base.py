"""Base definitions for build-log error signatures."""

import re
from dataclasses import dataclass, field


@dataclass
class SignatureMatch:
    """Represents a matched build log error signature."""

    signature_id: str
    line_number: int
    raw_line: str
    source: str
    category: str
    message: str
    is_root_cause_candidate: bool = False
    confidence: str = "Possible root cause"
    downstream_impacts: list[str] = field(default_factory=list)


class BaseSignature:
    """Base class for regex-based error signatures."""

    def __init__(
        self,
        signature_id: str,
        source: str,
        category: str,
        patterns: list[str],
        message_template: str,
        is_root_cause: bool = False,
        confidence: str = "Possible root cause",
    ) -> None:
        self.signature_id = signature_id
        self.source = source
        self.category = category
        self.regexes = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.message_template = message_template
        self.is_root_cause = is_root_cause
        self.confidence = confidence

    def match_line(self, line: str, line_number: int) -> SignatureMatch | None:
        """Test if the line matches any pattern of this signature."""
        for regex in self.regexes:
            m = regex.search(line)
            if m:
                # Format message with captured groups if present
                try:
                    formatted_msg = self.message_template.format(*m.groups(), **m.groupdict())
                except Exception:
                    formatted_msg = self.message_template

                return SignatureMatch(
                    signature_id=self.signature_id,
                    line_number=line_number,
                    raw_line=line.strip(),
                    source=self.source,
                    category=self.category,
                    message=formatted_msg,
                    is_root_cause_candidate=self.is_root_cause,
                    confidence=self.confidence,
                )
        return None
