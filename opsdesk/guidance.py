from pathlib import Path

import yaml


class GuidanceCatalog:
    def __init__(self, root):
        self.items = []
        for path in sorted(Path(root).glob("*/SKILL.md")):
            raw = path.read_text(encoding="utf-8")
            parts = raw.split("---", 2)
            if len(parts) != 3 or parts[0].strip():
                raise ValueError(f"Invalid Skill metadata: {path.name}")
            metadata = yaml.safe_load(parts[1])
            if not isinstance(metadata, dict) or not metadata.get("name") or not metadata.get("description"):
                raise ValueError(f"Skill lacks a name or description: {path.parent.name}")
            self.items.append({**metadata, "body": parts[2].strip()})

    def select(self, intake):
        return [item for item in self.items if intake.intent in item.get("intents", []) and (not item.get("categories") or intake.category in item["categories"])]

    def describe(self):
        return [{key: item[key] for key in ("name", "description", "intents")} for item in self.items]
