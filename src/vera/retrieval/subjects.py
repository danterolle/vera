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
    r"ingegneria sociale|hacker|defacement|privilege[\s-]?escalation|"
    r"powershell|sysinternals|wireshark|nmap|metasploit|mimikatz|"
    r"cobalt[\s-]?strike|burp[\s-]?suite|dns|tunnel(?:l)?ing)\b",
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


RELEVANCE_PREFIX = re.compile(
    r"^(?:"
    r"explain\s+the\s+defensive\s+measure\s+supplied\s+for\s+|"
    r"what\s+documented\s+action\s+reduces\s+the\s+risk\s+from\s+|"
    r"what\s+should\s+(?:a\s+defender|we)\s+"
    r"(?:know\s+about|deploy\s+first\s+against)\s+|"
    r"how\s+do\s+defenders\s+mitigate\s+|"
    r"which\s+mitigation\s+applies\s+to\s+|"
    r"review\s+the\s+pinned\s+record\s+for\s+|"
    r"revise\s+the\s+assessment\s+for\s+|"
    r"triage\s+|"
    r"how\s+(?:does|do|is|are|can|could|would|should)\s+|"
    r"why\s+(?:does|do|is|are|can|could|would|should)\s+|"
    r"what\s+(?:is|are|was|were|does|do)\s+(?:the\s+)?|"
    r"explain\s+(?:the\s+)?|describe\s+(?:the\s+)?|define\s+(?:the\s+)?|"
    r"tell\s+me\s+about\s+|analy[sz]e\s+(?:the\s+)?|"
    r"can\s+you\s+(?:define|explain|describe)\s+"
    r")",
    re.IGNORECASE,
)
RELEVANCE_TRAIL = re.compile(
    r"\s+(?:work|works|function|functions|mean|means|do|does|help|apply|applies|"
    r"matter|look\s+like)\s*[?!.]*$",
    re.IGNORECASE,
)
RELEVANCE_CLAUSE = re.compile(
    r"\s+(?:and(?=\s+(?:describe|explain)\b)|but|or|while|whereas|using|that|which|who)\s+", re.I,
)
GENERIC_SUBJECT_WORDS = {
    "a", "an", "the", "of", "to", "in", "on", "for", "from", "by", "as", "at",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "it", "its", "their", "there", "what", "how", "why", "when", "where",
    "which", "who", "whom", "whose", "do", "does", "did", "done", "can", "could",
    "should", "would", "may", "might", "must", "will", "shall", "about", "into",
    "over", "under", "between", "among", "during", "before", "after", "above",
    "below", "up", "down", "out", "off", "again", "further", "then", "once",
    "only", "own", "same", "so", "than", "too", "very", "just", "also", "not",
    "no", "yes", "if", "because", "while", "without", "within", "across", "per",
    "via", "attack", "attacks", "vulnerability", "vulnerabilities", "technique",
    "techniques", "issue", "issues", "problem", "problems", "record", "records",
    "documentation", "documented", "supplied", "evidence", "defender", "defenders",
}


def _spelling(value: str) -> str:
    """Fold common British doubling so tunnelling matches tunneling."""
    return value.replace("ll", "l")


def _subject_tokens(subject: str) -> list[str]:
    return [
        _spelling(word)
        for word in normalized(subject).split()
        if word and word not in GENERIC_SUBJECT_WORDS
    ]


def subject_candidates(query: str, current_subject: str | None = None) -> list[str]:
    """Candidate subjects used to decide whether any supplied record is on topic."""
    values: list[str] = []
    if current_subject:
        values.append(current_subject)
    values.extend(item.upper() for item in IDENTIFIERS.findall(query))
    text = re.split(r"[?!;]|\.(?:\s|$)", query.strip())[0]
    text = RELEVANCE_PREFIX.sub("", text).strip()
    text = re.sub(r"^(?:a|an|the)\s+", "", text, flags=re.IGNORECASE)
    text = RELEVANCE_TRAIL.sub("", text).strip(" .,:;-")
    values.extend(part.strip() for part in text.rsplit(":", 1)[1:])
    text = RELEVANCE_CLAUSE.split(text)[0].strip(" .,:;-")
    if text and len(text.split()) <= 9:
        values.append(text)
    if derived := concept_subject(query):
        values.append(derived)
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _names(item: Evidence) -> list[str]:
    if item.source == SourceType.MEMORY or item.status != EvidenceStatus.AVAILABLE:
        return []
    names = [item.title.split("—")[0], *item.metadata.get("aliases", [])]
    for entity in item.metadata.get("graph_entities", []):
        names.extend([entity.get("name", ""), *entity.get("aliases", [])])
    names += [str(item.metadata.get(key, "")) for key in
              ("external_id", "cve_id", "cwe_id", "technique_id")]
    return [str(name) for name in names if name]


def names_subject(item: Evidence, subject: str) -> bool:
    """A passing mention inside a relationship is not a definition of its target."""
    needle = normalized(subject)
    return bool(needle) and any(
        f" {needle} " in f" {normalized(name)} " for name in _names(item)
    )


def mentions_subject(item: Evidence, subject: str) -> bool:
    """Exact identifiers; for concepts, require every meaningful token in one name."""
    if IDENTIFIERS.fullmatch(subject.strip()):
        needle = normalized(subject)
        return any(f" {needle} " in f" {normalized(name)} " for name in _names(item))
    wanted = _subject_tokens(subject)
    if not wanted:
        return names_subject(item, subject)
    return any(
        all(
            f" {token} " in f" {_spelling(normalized(name))} "
            for token in wanted
        )
        for name in _names(item)
    )
