import re
from dataclasses import dataclass, field


@dataclass
class RedactionResult:
    text: str
    detections: list[str] = field(default_factory=list)

    @property
    def pii_detected(self) -> bool:
        return len(self.detections) > 0


_PATTERNS = [
    ("EMAIL", re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')),
    ("SSN",   re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ("CC",    re.compile(r'\b(?:\d{4}[\-\s]?){3}\d{4}\b')),
    ("PHONE", re.compile(r'\+?1?\s?(?:\(\d{3}\)|\d{3})[\-.\s]?\d{3}[\-.\s]?\d{4}')),
    ("IP",    re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')),
    ("NI",    re.compile(r'\b[A-Z]{2}\d{6}[A-Z]\b')),
]


def redact(text: str) -> RedactionResult:
    result = text
    detections: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(result):
            detections.append(label)
            result = pattern.sub(f"[REDACTED_{label}]", result)
    return RedactionResult(text=result, detections=detections)
