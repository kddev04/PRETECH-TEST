"""Create .env from .env.example with fresh random MySQL passwords. Never overwrites an existing .env."""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    env = ROOT / ".env"
    if env.exists():
        print("  .env already exists, left unchanged.")
        return 0
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("MYSQL_PASSWORD="):
            line = "MYSQL_PASSWORD=" + secrets.token_urlsafe(18)
        elif line.startswith("MYSQL_ROOT_PASSWORD="):
            line = "MYSQL_ROOT_PASSWORD=" + secrets.token_urlsafe(18)
        lines.append(line)
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  Created .env with new local MySQL passwords.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
