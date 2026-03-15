#!/usr/bin/env python3
"""
Generate agent-focused docs (contracts + API docstrings) without importing Seamless.

Inputs:
- docs/agent/public-api.json (curated public surface)

Outputs:
- docs/agent/api/**.md (API pages generated from docstrings via AST parsing)
- docs/agent/index.json (topic + symbol index for fast agent lookup)
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import shutil
import time
from dataclasses import dataclass
from typing import Iterable


ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = pathlib.Path(
    os.environ.get("WORKSPACE_DIR", str(ROOT.parent))
).resolve()
AGENT_DOCS = ROOT / "docs" / "agent"
PUBLIC_API = AGENT_DOCS / "public-api.json"
INDEX = AGENT_DOCS / "index.json"
API_DIR = AGENT_DOCS / "api"


_NON_WORD = re.compile(r"[^a-z0-9 _-]+")
_WS = re.compile(r"\s+")


def _slugify(heading: str) -> str:
    s = heading.strip().lower()
    s = s.replace(".", "-").replace("_", "-")
    s = _NON_WORD.sub("", s)
    s = _WS.sub("-", s)
    s = s.strip("-")
    return s


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _iter_contract_pages() -> list[pathlib.Path]:
    contracts_dir = AGENT_DOCS / "contracts"
    if not contracts_dir.exists():
        return []
    return sorted(p for p in contracts_dir.glob("*.md") if p.is_file())


def _format_args(args: ast.arguments) -> str:
    def _arg(a: ast.arg) -> str:
        return a.arg

    posonly = [_arg(a) for a in getattr(args, "posonlyargs", [])]
    regular = [_arg(a) for a in args.args]
    vararg = ("*" + args.vararg.arg) if args.vararg else None
    kwonly = [_arg(a) for a in args.kwonlyargs]
    kwarg = ("**" + args.kwarg.arg) if args.kwarg else None

    out: list[str] = []
    if posonly:
        out.extend(posonly)
        out.append("/")
    out.extend(regular)
    if vararg:
        out.append(vararg)
    elif kwonly:
        out.append("*")
    out.extend(kwonly)
    if kwarg:
        out.append(kwarg)
    return ", ".join(out)


def _signature_for(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{node.name}({_format_args(node.args)})"
    if isinstance(node, ast.ClassDef):
        return node.name
    return "<?>"


@dataclass(frozen=True)
class Symbol:
    qualname: str
    kind: str  # function|class|method
    signature: str
    doc: str


def _collect_symbols(module_name: str, tree: ast.Module) -> tuple[str, list[Symbol]]:
    module_doc = ast.get_docstring(tree) or ""
    symbols_by_qualname: dict[str, Symbol] = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            qualname = f"{module_name}.{node.name}"
            symbols_by_qualname[qualname] = Symbol(
                qualname=qualname,
                kind="function",
                signature=_signature_for(node),
                doc=doc,
            )
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            class_qualname = f"{module_name}.{node.name}"
            symbols_by_qualname[class_qualname] = Symbol(
                qualname=class_qualname,
                kind="class",
                signature=_signature_for(node),
                doc=doc,
            )
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name.startswith("_"):
                        continue
                    subdoc = ast.get_docstring(sub) or ""
                    qualname = f"{module_name}.{node.name}.{sub.name}"
                    symbols_by_qualname[qualname] = Symbol(
                        qualname=qualname,
                        kind="method",
                        signature=_signature_for(sub),
                        doc=subdoc,
                    )

    symbols = [symbols_by_qualname[k] for k in sorted(symbols_by_qualname.keys())]
    return module_doc, symbols


def _extract_dunder_all(tree: ast.Module) -> list[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                value = node.value
                if isinstance(value, (ast.List, ast.Tuple)):
                    items: list[str] = []
                    for elt in value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            items.append(elt.value)
                    return items
    return []


def _render_api_page(
    module_name: str,
    module_doc: str,
    symbols: Iterable[Symbol],
    *,
    exports: list[str] | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# {module_name}")
    if module_doc.strip():
        lines.append("")
        lines.append(module_doc.strip())
    if exports:
        lines.append("")
        lines.append("## Exports")
        lines.append("")
        lines.append(
            "This module primarily re-exports public primitives. Export list (`__all__`):"
        )
        lines.append("")
        for name in exports:
            lines.append(f"- `{name}`")
        lines.append("")
        lines.append(
            "For details, see the generated API pages for the underlying implementation modules."
        )

    for sym in symbols:
        heading = sym.qualname
        lines.append("")
        lines.append(f"## `{heading}`")
        lines.append("")
        lines.append(f"- kind: `{sym.kind}`")
        lines.append(f"- signature: `{sym.signature}`")
        if sym.doc.strip():
            lines.append("")
            lines.append(sym.doc.strip())
        else:
            lines.append("")
            lines.append("_No docstring._")
    lines.append("")
    return "\n".join(lines)


def _clean_api_dir() -> None:
    API_DIR.mkdir(parents=True, exist_ok=True)
    for p in API_DIR.rglob("*.md"):
        if p.name == ".gitkeep":
            continue
        p.unlink()
    for p in API_DIR.rglob(".gitkeep"):
        # keep marker file
        pass


def _load_public_api() -> dict:
    if not PUBLIC_API.exists():
        raise SystemExit(f"Missing {PUBLIC_API}")
    return json.loads(_read_text(PUBLIC_API))


def _generate_python_api(public_api: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    sources = public_api.get("python", {}).get("sources", [])
    for src in sources:
        module_name = src["module"]
        relpath = src["path"]
        candidate_paths = [
            ROOT / relpath,
            WORKSPACE_ROOT / relpath,
        ]
        abspath = next((p for p in candidate_paths if p.exists()), None)
        if abspath is None:
            raise SystemExit(f"Missing source file for {module_name}: {relpath}")
        tree = ast.parse(_read_text(abspath), filename=str(abspath))
        module_doc, symbols = _collect_symbols(module_name, tree)
        exports = _extract_dunder_all(tree) if relpath.endswith("__init__.py") else None
        page = _render_api_page(module_name, module_doc, symbols, exports=exports)
        page_path = API_DIR / "python" / f"{module_name}.md"
        _write_text(page_path, page)
        out[module_name] = str(page_path.relative_to(AGENT_DOCS))
    return out


def _generate_cli_docs(public_api: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    commands = public_api.get("cli", {}).get("commands", [])
    for cmd in commands:
        name = cmd["name"]
        contract = cmd.get("contract_page")
        lines = [
            f"# {name}",
            "",
            "Agent-facing contract lives in:",
            f"- `{contract}`" if contract else "- _(none)_",
            "",
            "Local usage (recommended):",
            f"- `{name} --help`",
            "",
        ]
        page_path = API_DIR / "cli" / f"{name}.md"
        _write_text(page_path, "\n".join(lines))
        out[name] = str(page_path.relative_to(AGENT_DOCS))
    return out


def _build_index(public_api: dict, api_pages: dict[str, str], cli_pages: dict[str, str]) -> None:
    index: dict = {"version": 1, "generated_at": int(time.time()), "topics": {}, "symbols": {}}

    # Topics: contracts
    contracts = _iter_contract_pages()
    index["topics"]["contracts"] = [
        str(p.relative_to(AGENT_DOCS)) for p in contracts
    ]

    # Topics: API pages
    index["topics"]["api_python"] = api_pages
    index["topics"]["api_cli"] = cli_pages

    # Symbols: best-effort from headings in API pages
    for module_name, relpage in api_pages.items():
        page_path = AGENT_DOCS / relpage
        text = _read_text(page_path)
        for line in text.splitlines():
            if not line.startswith("## `"):
                continue
            heading = line[len("## `") :].rstrip("`").strip()
            anchor = _slugify(heading)
            index["symbols"][heading] = {"page": relpage, "anchor": anchor}

    _write_text(INDEX, json.dumps(index, indent=2, sort_keys=True) + "\n")


def main() -> int:
    public_api = _load_public_api()
    _clean_api_dir()
    api_pages = _generate_python_api(public_api)
    cli_pages = _generate_cli_docs(public_api)
    _build_index(public_api, api_pages, cli_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
