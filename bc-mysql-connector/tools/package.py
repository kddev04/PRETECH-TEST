"""Build dist/pretech-connect.zip to copy onto another Windows machine.

Leaves out what must not travel: .venv (tied to this PC), .env (this PC's passwords),
APIWORK (reference sources), caches and local databases. On the new machine: unzip,
run setup.bat, then start-demo.bat.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "APIWORK", "__pycache__", ".pytest_cache", "dist", ".git"}
SKIP_FILES = {".env", "pretech_connect.db"}


def main() -> None:
    out = ROOT / "dist" / "pretech-connect.zip"
    out.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob("*")):
            rel = path.relative_to(ROOT)
            if any(part in SKIP_DIRS for part in rel.parts) or path.name in SKIP_FILES or path.suffix == ".pyc":
                continue
            if path.is_file():
                z.write(path, Path("pretech-connect") / rel)
                count += 1
    print(f"  {out}  ({count} files, {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
