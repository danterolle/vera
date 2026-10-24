"""Resolve a research subject without mixing the current and previous questions."""

import re
import unicodedata
from collections.abc import Sequence

from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence
from vera.domain.requests import ConversationMessage

CONCEPT_PREFIX = re.compile(
    r"^(?:(?:che\s+)?cos(?:a\s+[eè]|['’]?[eè])|what\s+(?:is|are)|"
    r"tell me about|define|explain|describe|definisci|descrivi|spiega(?:mi)?|"
    r"parlami\s+d(?:i|el|ella|ello|ell'|ei|egli|elle)?|dimmi\s+d(?:i|el|ella|ello|ell'|ei|egli|elle)?)\s+",
    re.IGNORECASE,
)
WEB_INTENT = re.compile(
    r"\b(?:(?:cerca|ricerca|cercare|cercami|search|look\s+up|browse|trova)\b.{0,40}"
    r"\b(?:internet|web|online)|(?:internet|web|online)\s+(?:search|research|ricerca))\b",
    re.IGNORECASE,
)
WEB_PREFIX = re.compile(
    r"^(?:per favore\s+)?(?:cerca|ricerca|cercare|cercami|search|look\s+up|browse|trova)\s*"
    r"(?:(?:su|in|on|the)\s+)*(?:internet|web|online)\s*[:,.!?\-]*\s*",
    re.IGNORECASE,
)
IDENTIFIERS = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,19}|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?|[SGM]\d{4})\b",
    re.IGNORECASE,
)
EXPLICIT_SECURITY_TOPIC = re.compile(
    r"\b(?:mitre|att&ck|cve|cwe|capec|"
    r"cyber[\s-]?(?:attack|attacco|security|sicurezza)|"
    r"attacc[oi] informatic[oi]|sicurezza informatica|"
    r"malware|ransomware|phishing|firewall|antivirus|edr|siem|soc|"
    r"vulnerabilit(?:à|a|y|ies)|exploit|zero-day|0-day|"
    r"rootkit|trojan|backdoor|spyware|adware|keylogger|worm|botnet|"
    r"ddos|dos|brute[\s-]?force|credential[\s-]?stuffing|"
    r"injection|sql[i]?|xss|csrf|ssrf|buffer[\s-]?overflow|"
    r"man-in-the-middle|mitm|spoofing|social[\s-]?engineering|"
    r"ingegneria sociale|hacker|defacement|privilege[\s-]?escalation)\b",
    re.IGNORECASE,
)


def explicit_security_topic(query: str) -> bool:
    """Explicit ATT&CK/CVE-style identifiers are not a conversational clarification."""
    return bool(IDENTIFIERS.search(query) or EXPLICIT_SECURITY_TOPIC.search(query))


def research_query(query: str, conversation: Sequence[ConversationMessage] = ()) -> str:
    """A standalone 'search online' refers to the last substantive user question."""
    cleaned = WEB_PREFIX.sub("", query).strip(" .?!")
    if WEB_INTENT.search(query):
        cleaned = re.sub(
            r"^(?:informazioni\s+su|information\s+about)\s+", "", cleaned, flags=re.I,
        )
        cleaned = re.split(
            r"(?:^|\s)(?:e|and)\s+(?:cita|usa|fornisci|mostra|rispondi|cite|use|answer)\b",
            cleaned, maxsplit=1, flags=re.I,
        )[0].strip()
    if cleaned:
        return cleaned[:512]
    for message in reversed(conversation):
        if message.role == "user" and not WEB_INTENT.search(message.content):
            return message.content[:512]
    return ""


def concept_subject(query: str) -> str | None:
    if not CONCEPT_PREFIX.match(query):
        return None
    identifiers = list(dict.fromkeys(item.upper() for item in IDENTIFIERS.findall(query)))
    if identifiers:
        return identifiers[0] if len(identifiers) == 1 else None
    subject = re.split(r"[?!;]|\.(?:\s|$)", CONCEPT_PREFIX.sub("", query))[0].strip()
    subject = re.sub(r"^(?:il|lo|la|un|uno|una|the|an|a)\s+", "", subject, flags=re.I)
    # Compound requests are not a single entity name; retain their broader context.
    if len(subject.split()) > 6 or re.search(r"\b(?:e|and|confronta|compare)\b", subject, re.I):
        return None
    return subject[:160] or None


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", value))


def names_subject(item: Evidence, subject: str) -> bool:
    """A passing mention inside a relationship is not a definition of its target."""
    if item.source == SourceType.MEMORY or item.status != EvidenceStatus.AVAILABLE:
        return False
    names = [item.title.split("—")[0], *item.metadata.get("aliases", [])]
    for entity in item.metadata.get("graph_entities", []):
        names.extend([entity.get("name", ""), *entity.get("aliases", [])])
    names += [str(item.metadata.get(key, "")) for key in (
        "external_id", "cve_id", "cwe_id", "technique_id",
    )]
    needle = normalized(subject)
    return bool(needle) and any(
        f" {needle} " in f" {normalized(str(name))} " for name in names
    )
