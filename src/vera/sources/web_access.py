import socket
from ipaddress import ip_address
from urllib.parse import urlsplit

PRIMARY_HOSTS = {
    "attack.mitre.org", "cwe.mitre.org", "capec.mitre.org", "www.cisa.gov", "cisa.gov",
    "nvd.nist.gov", "csrc.nist.gov", "owasp.org", "learn.microsoft.com",
    "msrc.microsoft.com", "github.com", "www.rfc-editor.org",
    "en.wikipedia.org", "it.wikipedia.org", "www.bleepingcomputer.com", "bleepingcomputer.com",
    "thehackernews.com", "darkreading.com", "krebsonsecurity.com",
    "www.mandiant.com", "mandiant.com", "www.crowdstrike.com", "crowdstrike.com",
    "www.sentinelone.com", "sentinelone.com", "csirt.gov.it", "www.csirt.gov.it", "cert.europa.eu",
}


def primary_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https" or parsed.hostname not in PRIMARY_HOSTS
            or parsed.username or parsed.password or parsed.port not in {None, 443}
            or len(url) > 2000
        ):
            return False
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ip_address(row[4][0]).is_global for row in addresses)
    except (ValueError, OSError):
        return False
