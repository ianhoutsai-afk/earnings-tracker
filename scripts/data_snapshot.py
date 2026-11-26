"""Pack or restore the same complete data bundle used by the update jobs."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FILES = (
    "data.json", "historical_data.json", "history_status.json",
    "official_history.json", "official_scan_state.json",
)


def pack(root: Path, destination: Path):
    with ZipFile(destination, "w") as archive:
        for name in FILES:
            # Fixed metadata keeps identical inputs byte-for-byte reproducible.
            archive.writestr(ZipInfo(name), (root / name).read_bytes(), ZIP_DEFLATED)


def restore(source: Path, root: Path):
    with ZipFile(source) as archive:
        if sorted(archive.namelist()) != sorted(FILES):
            raise ValueError("Snapshot has missing, duplicate or unexpected entries")
        contents = {name: archive.read(name) for name in FILES}

    for name, content in contents.items():
        expected = list if name in ("data.json", "official_history.json") else dict
        if not isinstance(json.loads(content), expected):
            raise ValueError(f"Unexpected JSON structure in {name}")

    for name, content in contents.items():
        (root / name).write_bytes(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("pack", "restore"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    if args.operation == "pack":
        pack(args.root, args.archive)
    else:
        restore(args.archive, args.root)
