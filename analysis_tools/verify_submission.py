"""Verify the exact report and supporting files accepted for submission (offline)."""

from cadence.config import Paths
from cadence.eval.provenance import sha256
from cadence.utils.io import read_json


def main():
    record = read_json(Paths.RESULTS / "acceptance/release.json")
    if record["status"] != "accepted" or record["pdf"]["pages"] != 6:
        raise ValueError("Submission acceptance is incomplete")
    if not all(c["status"] == "pass" for c in record["checks"]):
        raise ValueError("A submission check has not passed")
    for name, digest in record["input_hashes"].items():
        if sha256(Paths.ROOT / name) != digest:
            raise ValueError(f"Accepted artifact changed; review it again: {name}")
    pdf = Paths.ROOT / record["pdf"]["path"]
    if not pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Report is not a PDF")
    print(f"Verified {len(record['input_hashes'])} accepted files; six-page report hash matches")


if __name__ == "__main__":
    main()
