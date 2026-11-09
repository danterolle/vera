import hashlib
import json
from pathlib import Path

import httpx

ATTACK_REVISION = "c2494b29dd268c46a5d0ea0990553e4327cd2253"
KEV_REVISION = "fd12990e9c566a1ad3060e1a2073129778f438cc"
ROOT = "https://raw.githubusercontent.com"
SNAPSHOTS = {
    "attack": {
        "revision": ATTACK_REVISION,
        "url": f"{ROOT}/mitre-attack/attack-stix-data/{ATTACK_REVISION}"
               "/enterprise-attack/enterprise-attack.json",
        "license_url": f"{ROOT}/mitre-attack/attack-stix-data/{ATTACK_REVISION}/LICENSE.txt",
        "license": "MITRE ATT&CK license",
    },
    "kev": {
        "revision": KEV_REVISION,
        "url": f"{ROOT}/cisagov/kev-data/{KEV_REVISION}/known_exploited_vulnerabilities.json",
        "license_url": f"{ROOT}/cisagov/kev-data/{KEV_REVISION}/LICENSE",
        "license": "CC0-1.0",
    },
}


def download(client: httpx.Client, url: str, destination: Path, limit: int) -> None:
    temporary = destination.with_suffix(".partial")
    try:
        with client.stream("GET", url) as response, temporary.open("xb") as output:
            response.raise_for_status()
            count = 0
            for block in response.iter_bytes():
                count += len(block)
                if count > limit:
                    raise ValueError(f"Public source exceeds the {limit}-byte bound: {url}")
                output.write(block)
        temporary.rename(destination)
    finally:
        temporary.unlink(missing_ok=True)


def verify_snapshots(directory: Path, manifest: dict) -> None:
    if manifest["format_version"] != 1 or manifest["sources"] != SNAPSHOTS:
        raise ValueError("Public source revisions differ from the reproducible recipe")
    for filename, expected in manifest["files"].items():
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError("Invalid cached public snapshot path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Public snapshot checksum mismatch: {filename}")


def acquire_sources(directory: Path) -> dict:
    manifest_path = directory / "snapshots.json"
    if directory.exists():
        verify_snapshots(directory, json.loads(manifest_path.read_text()))
        return json.loads(manifest_path.read_text())
    directory.mkdir(parents=True)
    manifest = {"format_version": 1, "sources": {}, "files": {}}
    try:
        with httpx.Client(
            timeout=90, follow_redirects=False,
            headers={"User-Agent": "VERA/0.2 public defensive training dataset"},
        ) as client:
            for name, information in SNAPSHOTS.items():
                for url, filename, limit in (
                    (information["url"], f"{name}.json", 100_000_000),
                    (information["license_url"], f"{name}-LICENSE.txt", 50_000),
                ):
                    path = directory / filename
                    download(client, url, path, limit)
                    manifest["files"][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
                payload = json.loads((directory / f"{name}.json").read_text())
                if not isinstance(payload, dict):
                    raise ValueError(f"The {name} snapshot is not a JSON object")
                manifest["sources"][name] = information
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    except (httpx.HTTPError, OSError, ValueError):
        for filename in ("attack.json", "kev.json", "attack-LICENSE.txt", "kev-LICENSE.txt"):
            (directory / filename).unlink(missing_ok=True)
        directory.rmdir()
        raise
    return manifest
