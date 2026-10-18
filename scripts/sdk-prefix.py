"""Read the registered Cwhip SDK prefix without evaluating user configuration."""

import os
from pathlib import Path
import sys


def settings_path():
    config_home = os.environ.get("XDG_CONFIG_HOME", "")
    if not config_home:
        home = os.environ.get("HOME", "")
        if not home:
            return None
        config_home = os.path.join(home, ".config")
    if not os.path.isabs(config_home):
        raise ValueError(
            f"XDG_CONFIG_HOME must be absolute to discover the Cwhip SDK: {config_home}"
        )
    return Path(config_home) / "cwhip" / "settings.toml"


def read_prefix(settings):
    try:
        import tomllib
    except ModuleNotFoundError as error:
        raise RuntimeError("reading sdk_prefix requires Python 3.11 or newer") from error

    try:
        with settings.open("rb") as stream:
            config = tomllib.load(stream)
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as error:
        raise ValueError(f"{settings}: cannot read sdk_prefix: {error}") from error

    if "sdk_prefix" not in config:
        return ""
    prefix = config["sdk_prefix"]
    if (
        not isinstance(prefix, str)
        or not prefix
        or any(character in prefix for character in "\0\r\n")
        or not os.path.isabs(prefix)
        or not os.path.isdir(prefix)
    ):
        raise ValueError(
            f"{settings}: sdk_prefix must be a non-empty absolute path to an "
            "existing SDK installation directory (without NUL or line breaks)"
        )
    return prefix


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "--discover":
            settings = settings_path()
            prefix = "" if settings is None else read_prefix(settings)
        elif len(sys.argv) == 2:
            prefix = read_prefix(Path(sys.argv[1]))
        else:
            print(f"Usage: {sys.argv[0]} [--discover|settings.toml]", file=sys.stderr)
            return 2
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    sys.stdout.write(prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
