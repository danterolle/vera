import re

CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,19}\b", re.IGNORECASE)


def extract_cve_ids(text: str) -> list[str]:
    return sorted({match.upper() for match in CVE_PATTERN.findall(text)})
