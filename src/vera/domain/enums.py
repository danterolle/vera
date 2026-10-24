from enum import StrEnum


class Route(StrEnum):
    CAG_ONLY = "CAG_ONLY"
    CAG_RAG = "CAG_RAG"
    CAG_RAG_TOOL = "CAG_RAG_TOOL"
    STREAM = "STREAM"
    FULL = "FULL"


class SourceType(StrEnum):
    CAG = "cag"
    CAPEC = "capec"
    CISA_KEV = "cisa_kev"
    CVE_ORG = "cve_org"
    CWE = "cwe"
    FIRST_EPSS = "first_epss"
    MITRE_ATTACK = "mitre_attack"
    NIST = "nist"
    NVD = "nvd"
    OSV = "osv"
    OWASP = "owasp"
    STREAM = "stream"
    MEMORY = "memory"
    WEB = "web"


class EvidenceStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    SIMULATED = "simulated"


class ClaimStatus(StrEnum):
    SUPPORTED_FACT = "supported_fact"
    SYSTEM_INFERENCE = "system_inference"
    UNAVAILABLE = "unavailable"
    SIMULATED = "simulated"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}
