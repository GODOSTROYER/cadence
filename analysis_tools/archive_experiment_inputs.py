"""Preserve available frozen dependencies without changing historical results.

Run once before changing active configuration. Re-running verifies the append-only
archive records. No API calls, predictions or frozen manifests are changed.
"""

from __future__ import annotations

import argparse
import json

from cadence.config import Paths
from cadence.eval.archive import archive_inputs
from cadence.utils.io import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", action="append", help="Repository-relative result directory; repeatable")
    args = parser.parse_args()
    directories = ([Paths.ROOT / name for name in args.experiment] if args.experiment else
                   sorted(path.parent for path in Paths.RESULTS.glob("*/manifest.json")
                          if path.parent.name.startswith(("balanced_", "quality_"))))
    for directory in directories:
        manifest = read_json(directory / "manifest.json")
        record = archive_inputs(directory, manifest["frozen"]["inputs"])
        counts = {storage: sum(item["storage"] == storage for item in record["inputs"].values())
                  for storage in ("source_snapshot", "shared_archive", "verified_root")}
        print(json.dumps({"experiment": directory.name, **counts, "new_model_calls": 0}))


if __name__ == "__main__":
    main()
