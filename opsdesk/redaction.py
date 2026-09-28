import re


RULES = [
    (r"(?im)((?:password|passwd|api[_ -]?key|密码|验证码)\s*[:=：]\s*)[^\s，,；;]+", r"\1[REDACTED]"),
    (r"(?i)Bearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]"),
    (r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b", "[REDACTED_KEY]"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]"),
    (r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)", "[REDACTED_PHONE]"),
    (r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
]


def clean_text(value):
    for pattern, replacement in RULES:
        value = re.sub(pattern, replacement, value)
    return value.strip()
