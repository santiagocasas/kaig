#!/usr/bin/env python3
import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    db_dir = sys.argv[1]
    try:
        entries = [os.path.join(db_dir, name) for name in os.listdir(db_dir)]
    except FileNotFoundError:
        return 0
    removed = []
    for path in entries:
        try:
            if not os.access(path, os.W_OK):
                os.remove(path)
                removed.append(path)
        except IsADirectoryError:
            continue
        except Exception:
            continue
    if removed:
        print("Cleaned unwritable DB files:")
        for path in removed:
            print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
