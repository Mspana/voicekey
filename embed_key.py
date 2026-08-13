#!/usr/bin/env python3
"""Write a build-time copy of config.json with the API key filled in.

This is CONVENIENCE, NOT SECURITY. A PyInstaller one-file exe is an archive:
anyone with the file can unpack it and read the key. Use a key that is scoped
and budget-capped, and rotate it if the exe travels further than intended.

    python embed_key.py sk-...      -> writes build-config.json
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("usage: python embed_key.py sk-...")
        return 1
    key = sys.argv[1].strip()
    if not key.startswith("sk-"):
        print("that does not look like an OpenAI key (they start sk-)")
        return 1

    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    cfg["api_key"] = key
    out = HERE / "build-config.json"
    out.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.name} (key ends ...{key[-4:]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
