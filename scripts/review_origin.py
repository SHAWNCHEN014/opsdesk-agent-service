"""Post-implementation source comparison; this is evidence, not a legal decision."""
import argparse
import ast
import copy
from difflib import SequenceMatcher
import hashlib
import io
import json
from pathlib import Path
import re
import tokenize


def items(root):
    excluded = {".venv", "var", "data", "artifacts", "third-party", "models", ".git", "__pycache__", ".pytest_cache", ".uploads"}
    return [file for file in sorted(root.rglob("*")) if file.is_file() and not excluded.intersection(file.relative_to(root).parts) and file.suffix in {".py", ".js", ".html", ".css", ".md", ".svg"}]


def tokens(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline) if token.type not in {tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER}]
    return re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[\u4e00-\u9fff]+|\d+|[^\s]", text)


class Rename(ast.NodeTransformer):
    def generic_visit(self, node):
        node = super().generic_visit(node)
        for field, value in ast.iter_fields(node):
            if isinstance(value, str):
                if field in {"id", "arg", "attr", "name", "value"}:
                    setattr(node, field, "<normalized>")
        if hasattr(node, "body") and isinstance(node.body, list) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:]
        return node


def functions(path):
    if path.suffix != ".py":
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(list(ast.walk(node))) >= 60:
            result.append({"name": node.name, "line": node.lineno, "normalized": ast.dump(Rename().visit(copy.deepcopy(node)), include_attributes=False)})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("--output", type=Path, default=Path("docs/source-comparison.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    current, reference = items(root), items(args.reference)
    old_records = [(file, tokens(file), functions(file)) for file in reference]
    comparisons, exact_files, matches = [], [], []
    for file in current:
        best_score, best_file = 0, ""
        source = file.read_bytes()
        pieces, units = tokens(file), functions(file)
        for old, old_tokens, old_units in old_records:
            if source == old.read_bytes():
                exact_files.append({"candidate": str(file.relative_to(root)), "reference": str(old.relative_to(args.reference))})
            if old.suffix == file.suffix:
                score = SequenceMatcher(None, pieces, old_tokens, autojunk=False).ratio()
                if score > best_score:
                    best_score, best_file = score, str(old.relative_to(args.reference))
            for unit in units:
                for old_unit in old_units:
                    if unit["normalized"] == old_unit["normalized"]:
                        matches.append({"candidate": str(file.relative_to(root)), "function": unit["name"], "line": unit["line"], "reference": str(old.relative_to(args.reference)), "reference_function": old_unit["name"]})
        comparisons.append({"candidate": str(file.relative_to(root)), "most_similar_reference": best_file, "token_similarity": round(best_score, 4), "sha256": hashlib.sha256(source).hexdigest()})
    report = {"method": "All-pairs token comparison within file types; exact normalized AST comparison for functions with >=60 AST nodes. Names and string constants normalized for AST only. Dependencies excluded.", "limitation": "Earlier source was seen during an audit; this is not a legally isolated clean-room process. Scores alone do not determine copyright or contract compliance.", "candidate_files": len(current), "reference_files": len(reference), "identical_files": exact_files, "matching_normalized_functions": matches, "comparisons": sorted(comparisons, key=lambda row: -row["token_similarity"])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"candidate_files": len(current), "reference_files": len(reference), "identical_files": len(exact_files), "matching_normalized_functions": len(matches), "max_token_similarity": max(item["token_similarity"] for item in comparisons)}))


if __name__ == "__main__":
    main()
