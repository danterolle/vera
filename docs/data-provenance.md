# Data provenance and limitations

## Authoritative sources

| Source | Use | Access |
| --- | --- | --- |
| CVE.org | CNA-authored CVE List V5 record | Exact official CVE Record API lookup |
| NVD | CVE description, dates, and CVSS | Exact CVE API lookup |
| CISA KEV | Known-exploited catalog membership | Published JSON catalog |
| FIRST EPSS | Time-stamped exploitation probability | Exact CVE API lookup |
| OSV | Vulnerability aliases and ecosystem records | Exact identifier lookup |
| MITRE ATT&CK | Techniques, tactics, groups, software, and mitigations | Bundled subset or synchronized STIX |
| MITRE CWE and CAPEC | Weaknesses and attack patterns | Bundled focused subset |
| OWASP Top 10 | Web application risk categories | Bundled focused subset |
| NIST and FIRST | Stable definitions and guidance | Versioned CAG entries |

Local documents carry source URLs. Bundled NVD examples contain a `snapshot_date` and must not
be interpreted as current. Set `VERA_LIVE_SOURCES=true` for current exact lookups. Synchronized
feed manifests retain source URL, upstream version, document count, and retrieval timestamp.
Evidence metadata distinguishes live APIs, synchronized feeds, and bundled snapshots so only
logical duplicates from the same source and CVE are replaced.

## Interpretation rules

`supported_fact` requires an available citation from a source other than memory. Detection
rules and correlations are `system_inference`. Event data explicitly labeled as simulated
produces `simulated` findings. Disabled, missing, rate-limited, or failed sources produce
`unavailable` findings.

CVSS describes intrinsic severity and EPSS estimates exploitation probability. Neither is an
asset-specific risk score. CISA KEV membership indicates evidence of exploitation and does not
prove exploitation in the analyzed environment.

## Controlled stream scope

The prototype detects:

- network service discovery across ten ports within sixty seconds;
- five HTTP authentication failures within five minutes;
- twenty SYN packets without ACK within ten seconds;
- selected path traversal, command injection, and JNDI lookup markers.

Thresholds and time windows are configurable through `VERA_*` settings.

These rules are transparent teaching examples. They can produce false positives and false
negatives. Analysts must validate findings against complete packet, endpoint, identity, and
asset telemetry.

## Operational limitations

- The bundled corpus is focused rather than exhaustive; explicit sync provides complete
  current Enterprise ATT&CK and CISA KEV datasets.
- CWE, CAPEC, OWASP, and NIST remain curated subsets, not complete mirrors.
- Live API availability, quotas, and upstream schemas are outside VERA's control.
- The deterministic provider summarizes evidence but does not provide open-ended reasoning.
- External model quality depends on the selected model and endpoint.
- Quotation grounding is lexical and conservative; it does not provide complete NLI.
- PCAP analysis only uses fields exported by the installed `tshark`.
- The SQLite design targets a local prototype, not concurrent SOC-scale ingestion.
