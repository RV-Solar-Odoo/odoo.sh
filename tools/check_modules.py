#!/usr/bin/env python3
"""Validate that every int_* addon in this repo can actually be loaded by Odoo.

Odoo.sh builds whatever lands on a branch, and a module whose manifest points at a
file that is not there takes the whole database down with an internal server error.
This catches that before it is pushed.

    python3 tools/check_modules.py              # check the working tree
    python3 tools/check_modules.py --rev HEAD   # check a commit's tree instead

Checking a revision matters: a partial commit can leave a broken tree even when the
files on disk are fine.
"""

import argparse
import ast
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

MODULE_PREFIX = "int_"
PATH_KEYS = ("data", "demo", "init_xml", "update_xml")


class Tree:
    """Reads files either from disk or from a git revision."""

    def __init__(self, rev=None):
        self.rev = rev
        if rev:
            out = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", rev],
                capture_output=True, text=True, check=True,
            ).stdout
            self._files = set(out.splitlines())
        else:
            self._files = None

    def exists(self, path):
        if self.rev:
            return path in self._files
        return os.path.exists(path)

    def read(self, path):
        if self.rev:
            return subprocess.run(
                ["git", "show", f"{self.rev}:{path}"],
                capture_output=True, text=True, check=True,
            ).stdout
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def walk(self, suffix):
        if self.rev:
            return sorted(f for f in self._files if f.endswith(suffix))
        found = []
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]
            for name in files:
                if name.endswith(suffix):
                    found.append(os.path.relpath(os.path.join(root, name), "."))
        return sorted(found)

    def modules(self):
        return sorted(
            os.path.dirname(f)
            for f in self.walk("__manifest__.py")
            if os.path.dirname(f).startswith(MODULE_PREFIX) and "/" not in os.path.dirname(f)
        )


def check(tree):
    problems = []
    modules = tree.modules()
    if not modules:
        problems.append("no int_* modules found — is this the repo root?")

    for module in modules:
        manifest_path = f"{module}/__manifest__.py"
        try:
            manifest = ast.literal_eval(tree.read(manifest_path))
        except Exception as exc:
            problems.append(f"{manifest_path}: cannot parse ({exc})")
            continue

        if not tree.exists(f"{module}/__init__.py"):
            problems.append(f"{module}: missing __init__.py")

        for key in PATH_KEYS:
            for rel in manifest.get(key, []):
                if not tree.exists(f"{module}/{rel}"):
                    problems.append(f"{module}: manifest {key} lists missing '{rel}'")

        for bundle, paths in (manifest.get("assets") or {}).items():
            for entry in paths:
                path = entry[0] if isinstance(entry, (list, tuple)) else entry
                if any(ch in path for ch in "*[") or not path.startswith(MODULE_PREFIX):
                    continue
                if not tree.exists(path):
                    problems.append(f"{module}: asset bundle {bundle} lists missing '{path}'")

        for dep in manifest.get("depends", []):
            if dep.startswith(MODULE_PREFIX) and dep not in modules:
                problems.append(f"{module}: depends on '{dep}', which is not in this repo")

        for hook in ("post_init_hook", "pre_init_hook", "uninstall_hook"):
            name = manifest.get(hook)
            if name and name not in tree.read(f"{module}/__init__.py"):
                problems.append(f"{module}: {hook} '{name}' is not defined in __init__.py")

    for path in tree.walk(".py"):
        if not path.startswith(MODULE_PREFIX) and not path.startswith("tools/"):
            continue
        try:
            compile(tree.read(path), path, "exec")
        except SyntaxError as exc:
            problems.append(f"{path}: syntax error line {exc.lineno}: {exc.msg}")

    for path in tree.walk(".xml"):
        if not path.startswith(MODULE_PREFIX):
            continue
        try:
            ET.fromstring(tree.read(path))
        except ET.ParseError as exc:
            problems.append(f"{path}: invalid XML ({exc})")

    return modules, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rev", help="git revision to check instead of the working tree")
    args = parser.parse_args()

    tree = Tree(args.rev)
    modules, problems = check(tree)

    label = args.rev or "working tree"
    if problems:
        print(f"FAILED ({label}) — {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"OK ({label}) — {len(modules)} module(s): {', '.join(modules)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
