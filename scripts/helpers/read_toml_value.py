#!/usr/bin/env python3
import sys
import tomllib


def main() -> int:
    if len(sys.argv) < 3:
        return 2
    path = sys.argv[1]
    key = sys.argv[2]
    try:
        with open(path, "rb") as file:
            data = tomllib.load(file)
    except Exception:
        return 0
    value = data.get(key)
    if isinstance(value, str):
        sys.stdout.write(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
