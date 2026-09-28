"""Record licence metadata and preserve licence files from the installed distributions."""
import csv
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "third-party"
    output.mkdir(exist_ok=True)
    inventory = []
    for package in sorted(distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
        name = package.metadata.get("Name", "unknown")
        expression = package.metadata.get("License-Expression") or package.metadata.get("License") or "; ".join(v for v in package.metadata.get_all("Classifier", []) if v.startswith("License ::")) or "See archived licence or upstream metadata"
        license_files = []
        for relative in package.files or []:
            if not re.search(r"(?:^|/)(?:licen[cs]e|copying|notice|copyright)[^/]*$", str(relative), re.I):
                continue
            source = Path(package.locate_file(relative))
            if not source.is_file():
                continue
            safe = Path(str(relative))
            if ".." in safe.parts or safe.is_absolute():
                continue
            destination = output / "licenses" / name / safe
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            destination.write_bytes(data)
            license_files.append({"path": str(destination.relative_to(root)), "sha256": hashlib.sha256(data).hexdigest()})
        inventory.append({"name": name, "version": package.version, "license_metadata": expression, "homepage": package.metadata.get("Home-page") or "; ".join(package.metadata.get_all("Project-URL", [])), "files": license_files})
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    with (output / "inventory.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "version", "license_metadata", "homepage", "archived_files"])
        writer.writeheader()
        for item in inventory:
            writer.writerow({**{key: item[key] for key in writer.fieldnames[:-1]}, "archived_files": len(item["files"])})
    print(json.dumps({"distributions": len(inventory), "licence_files": sum(len(item["files"]) for item in inventory)}))


if __name__ == "__main__":
    main()
