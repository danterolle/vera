import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vera_domain.audit import audit_domain_dataset  # noqa: E402
from vera_domain.build import build_domain_dataset  # noqa: E402
from vera_domain.models import file_hash  # noqa: E402


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Build a public-evidence VERA v4 dataset; no training.",
    )
    parser.add_argument(
        "--snapshots", type=Path, default=root / ".vera/datasets/public-snapshots-v1",
    )
    parser.add_argument("--bundled", type=Path, default=root / "src/vera/data/corpus")
    parser.add_argument(
        "--output", type=Path, default=root / ".vera/datasets/vera-domain-v4",
    )
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--card", type=Path, default=root / "docs/domain-dataset-v4.md")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--token-budget", type=Path)
    args = parser.parse_args()
    archive = args.archive or args.output.with_suffix(".zip")
    if args.output.exists() or archive.exists():
        parser.error("Choose a new output directory; the dataset or archive already exists")
    manifest = build_domain_dataset(
        args.snapshots, args.output, bundled=args.bundled,
        seed=args.seed, card=args.card,
    )
    report = audit_domain_dataset(args.output)
    (args.output / "quality-report.json").write_text(json.dumps(report, ensure_ascii=True) + "\n")
    if args.token_budget is not None:
        _token_budget(args.output, args.token_budget)
    package = {"format_version": 1, "purpose": manifest["purpose"],
               "training_authorized": False, "files": {}}
    package["files"] = {
        str(path.relative_to(args.output)): file_hash(path)
        for path in sorted(args.output.rglob("*")) if path.is_file()
    }
    (args.output / "package.json").write_text(json.dumps(package, ensure_ascii=True) + "\n")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(args.output.rglob("*")):
            if path.is_file():
                output.write(path, str(path.relative_to(args.output)))
    print(f"Candidate dataset: {archive.resolve()}")
    print(json.dumps({
        split: {
            "conversations": values["examples"],
            "distinct_factual_texts": values["unique_factual_texts"],
            "multi_evidence_answers": values["multi_evidence_answers"],
            "alert_counts": values["alert_counts"],
            "intents": values["intents"],
        } for split, values in report["splits"].items()
    }, indent=2))
    print("This archive is data only. No model weights were loaded or trained.")


def _token_budget(directory: Path, receipt: Path) -> None:
    verification = json.loads(receipt.read_text())
    if (
        verification["dataset_sha256"] != file_hash(directory / "manifest.json")
        or verification.get("assistant_loss_mask_verified") is not True
        or verification.get("truncation") is not False
    ):
        raise ValueError("The token-budget receipt does not match this dataset")
    shutil.copyfile(receipt, directory / "token-budget.json")


if __name__ == "__main__":
    main()
