"""Shared logging utility helpers."""


def sanitize_context_for_log(custom_context: str, max_len: int = 120) -> str:
    """Truncate user-supplied context before writing to logs.

    Prevents sensitive or excessively long strings from polluting log output.
    """
    if not custom_context:
        return ""
    compact = " ".join(str(custom_context).split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len]}... ({len(compact)} chars)"
