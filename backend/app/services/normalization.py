import re


SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return SPACE_RE.sub(" ", value.strip().lower())


def first_present(row: dict[str, str], *keys: str) -> str | None:
    lowered = {key.strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
