#!/usr/bin/env python3
"""Download the Vazirmatn font (SIL OFL 1.1) into ../fonts if missing."""
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master"
FILES = {
    "fonts/ttf/Vazirmatn-Regular.ttf": "Vazirmatn-Regular.ttf",
    "fonts/ttf/Vazirmatn-Bold.ttf": "Vazirmatn-Bold.ttf",
    "OFL.txt": "OFL.txt",
}


def main() -> None:
    fonts_dir = Path(__file__).resolve().parent.parent / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    for remote, local in FILES.items():
        dest = fonts_dir / local
        if dest.exists() and dest.stat().st_size > 1000:
            print(f"✓ {local} از قبل هست")
            continue
        print(f"⬇ {local} ...")
        urllib.request.urlretrieve(f"{BASE}/{remote}", dest)
        print(f"✓ {local} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
