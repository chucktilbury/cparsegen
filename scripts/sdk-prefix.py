"""Read the registered Cwhip SDK prefix without evaluating user configuration."""

import os
from pathlib import Path
import sys


def config_home():
    selected_home = os.environ.get("XDG_CONFIG_HOME", "")
    if not selected_home:
        home = os.environ.get("HOME", "")
        if not home:
            return None
        selected_home = os.path.join(home, ".config")
    if not os.path.isabs(selected_home):
        raise ValueError(f"Selected config home must be absolute: {selected_home}")
    return Path(selected_home)


def registered_config_path():
    home = config_home()
    if home is None:
        return None
    directory = home / "cwhip"
    sdk_config = directory / "sdk.toml"
    legacy_config = directory / "settings.toml"
    if os.path.lexists(sdk_config):
        return sdk_config
    if os.path.lexists(legacy_config):
        return legacy_config
    return None


def read_prefix(config_file):
    try:
        import tomllib
    except ModuleNotFoundError as error:
        raise RuntimeError("reading sdk_prefix requires Python 3.11 or newer") from error

    try:
        with config_file.open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, ValueError) as error:
        raise ValueError(
            f"{config_file}: cannot read sdk_prefix: {error}"
        ) from error

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
            f"{config_file}: sdk_prefix must be a non-empty absolute path to an "
            "existing SDK installation directory (without NUL or line breaks)"
        )
    return prefix


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "--discover":
            config_file = registered_config_path()
            prefix = "" if config_file is None else read_prefix(config_file)
        elif len(sys.argv) == 2:
            prefix = read_prefix(Path(sys.argv[1]))
        else:
            print(
                f"Usage: {sys.argv[0]} [--discover|sdk.toml|settings.toml]",
                file=sys.stderr,
            )
            return 2
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    sys.stdout.write(prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
