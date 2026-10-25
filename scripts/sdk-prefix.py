"""Read the installed SDK prefix without evaluating user configuration."""

import os
from pathlib import Path
import sys


def main():
    settings = Path(sys.argv[1])
    try:
        import tomllib
    except ModuleNotFoundError:
        print(
            f"{settings}: reading sdk_prefix requires Python 3.11 or newer",
            file=sys.stderr,
        )
        return 1

    try:
        with settings.open("rb") as stream:
            config = tomllib.load(stream)
        if "sdk_prefix" not in config:
            return 0
        prefix = config["sdk_prefix"]
        if (
            not isinstance(prefix, str)
            or not prefix
            or any(character in prefix for character in "\0\r\n")
            or not os.path.isabs(prefix)
            or not os.path.isdir(prefix)
        ):
            raise ValueError(
                "sdk_prefix must be a non-empty absolute path to an existing SDK "
                "installation directory (without NUL or line breaks)"
            )
    except (OSError, ValueError) as error:
        print(f"{settings}: cannot read sdk_prefix: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
