"""Exercise Cwhip SDK discovery through the real project CMake file."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SdkDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "src").mkdir()
        shutil.copy2(ROOT / "CMakeLists.txt", self.project)
        shutil.copy2(ROOT / ".project_env", self.project)
        shutil.copy2(ROOT / "scripts/setup", self.project / "scripts")
        shutil.copy2(ROOT / "scripts/sdk-prefix.py", self.project / "scripts")
        (self.project / "src/main.cw").write_text("start {}\n")
        self.home = self.root / "home"
        self.home.mkdir()
        self.settings = self.home / ".config/cwhip/settings.toml"
        self.build = self.project / "build"
        self.env = os.environ.copy()
        for name in ("CWHIP_SDK", "CMAKE_PREFIX_PATH", "XDG_CONFIG_HOME"):
            self.env.pop(name, None)
        self.env["HOME"] = str(self.home)
        self.env["CMAKE_PREFIX_PATH"] = str(self.make_sdk("fallback"))

    def make_sdk(self, name):
        prefix = self.root / name
        package = prefix / "lib/cmake/Cwhip"
        package.mkdir(parents=True)
        (package / "CwhipConfig.cmake").write_text(
            'get_filename_component(prefix "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)\n'
            'file(WRITE "${CMAKE_BINARY_DIR}/selected-sdk.txt" "${prefix}")\n'
            'set(Cwhip_APPLICATION_OUTPUT_DIRECTORIES TRUE)\n'
            'function(cwhip_add_program name)\n'
            '  add_custom_target("${name}")\n'
            '  set_target_properties("${name}" PROPERTIES CWHIP_EXECUTABLE "${CMAKE_BINARY_DIR}/app")\n'
            'endfunction()\n'
        )
        (package / "CwhipConfigVersion.cmake").write_text(
            'set(PACKAGE_VERSION "0.0.1")\n'
            'set(PACKAGE_VERSION_COMPATIBLE TRUE)\n'
            'set(PACKAGE_VERSION_EXACT TRUE)\n'
        )
        return prefix

    def select(self, prefix):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(f"sdk_prefix = {json.dumps(str(prefix))}\n")

    def configure(self, success=True, extra=()):
        result = subprocess.run(
            ["cmake", "-S", str(self.project), "-B", str(self.build), *extra],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
            return (self.build / "selected-sdk.txt").read_text()
        self.assertNotEqual(result.returncode, 0, output)
        return output

    def test_registered_sdk_precedes_normal_discovery_and_stale_cache(self):
        selected = self.make_sdk("registered")
        self.select(selected)
        stale = self.make_sdk("stale") / "lib/cmake/Cwhip"
        self.assertEqual(
            self.configure(extra=[f"-DCwhip_DIR={stale}"]),
            str(selected),
        )

    def test_explicit_sdk_precedes_registered_sdk(self):
        self.select(self.make_sdk("registered"))
        selected = self.make_sdk("explicit")
        self.env["CWHIP_SDK"] = str(selected)
        self.assertEqual(self.configure(), str(selected))

    def test_empty_settings_falls_back_to_cmake_discovery(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))

    def test_invalid_registered_setting_fails_instead_of_falling_back(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('sdk_prefix = "relative"\n')
        output = self.configure(success=False)
        self.assertIn("sdk_prefix", output)
        self.assertIn("settings.toml", output)

    def test_xdg_settings_override_home_settings(self):
        home_sdk = self.make_sdk("home")
        self.select(home_sdk)
        xdg = self.root / "xdg"
        xdg_settings = xdg / "cwhip/settings.toml"
        xdg_settings.parent.mkdir(parents=True)
        xdg_sdk = self.make_sdk("xdg")
        xdg_settings.write_text(f"sdk_prefix = {json.dumps(str(xdg_sdk))}\n")
        self.env["XDG_CONFIG_HOME"] = str(xdg)
        self.assertEqual(self.configure(), str(xdg_sdk))

    def test_setup_uses_registered_prefix_for_cmake_and_shell_path(self):
        prefix = self.make_sdk("registered")
        self.select(prefix)
        tools = self.root / "tools"
        tools.mkdir()
        record = self.root / "shell-path.txt"
        fake_bash = tools / "bash"
        fake_bash.write_text(
            "#!/bin/sh\n"
            '/bin/bash --noprofile --norc -c \'source "$1"; printf "%s" "$PATH" > "$SHELL_RECORD"\' '
            '_ "$2"\n'
        )
        fake_bash.chmod(0o755)
        self.env["PATH"] = f"{tools}:{self.env['PATH']}"
        self.env["SHELL_RECORD"] = str(record)
        result = subprocess.run(
            ["/bin/bash", str(self.project / "scripts/setup")],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.build / "selected-sdk.txt").read_text(), str(prefix))
        self.assertEqual(record.read_text().split(":")[:3], [
            str(self.project / "bin"),
            str(self.project / "scripts"),
            str(prefix / "bin"),
        ])

    def test_missing_settings_does_not_create_user_configuration(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertFalse(self.settings.exists())


if __name__ == "__main__":
    unittest.main()
