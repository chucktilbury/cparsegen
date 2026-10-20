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
        self.sdk_settings = self.home / ".config/cwhip/sdk.toml"
        self.settings = self.home / ".config/cwhip/settings.toml"
        self.build = self.project / "build"
        self.env = os.environ.copy()
        for name in ("CWHIP_SDK", "CMAKE_PREFIX_PATH", "Cwhip_DIR", "XDG_CONFIG_HOME"):
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

    def select(self, prefix, settings=None):
        settings = settings or self.sdk_settings
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(f"sdk_prefix = {json.dumps(str(prefix))}\n")

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

    def test_explicit_sdk_bypasses_invalid_registration(self):
        self.sdk_settings.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_settings.write_text("invalid = [\n")
        selected = self.make_sdk("explicit SDK 'quoted'")
        self.env["CWHIP_SDK"] = str(selected)
        self.env["XDG_CONFIG_HOME"] = "relative"
        self.assertEqual(self.configure(), str(selected))

    def test_registered_prefix_with_spaces_and_quotes(self):
        selected = self.make_sdk('registered SDK "quoted"')
        self.select(selected)
        self.assertEqual(self.configure(), str(selected))

    def test_sdk_toml_only_discovery(self):
        selected = self.make_sdk("registered")
        self.select(selected)
        self.env.pop("CMAKE_PREFIX_PATH")
        self.assertEqual(self.configure(), str(selected))

    def test_sdk_settings_without_prefix_uses_normal_discovery_not_legacy(self):
        self.settings.parent.mkdir(parents=True)
        legacy = self.make_sdk("legacy")
        self.select(legacy, self.settings)
        self.sdk_settings.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_settings.write_text('[application]\nsdk_prefix = "not top level"\n')
        self.assertEqual(self.configure(), str(self.root / "fallback"))

    def test_invalid_explicit_selection_does_not_reuse_cached_sdk(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        for prefix in ("relative", str(self.root / "absent"), str(self.home)):
            with self.subTest(prefix=prefix):
                self.env["CWHIP_SDK"] = prefix
                output = self.configure(success=False)
                self.assertIn("CWHIP_SDK", output)
                self.assertIn("doc/BUILDING.md", output)

    def test_invalid_registered_package_does_not_reuse_cached_sdk(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.select(self.home, self.settings)
        output = self.configure(success=False)
        self.assertIn("sdk_prefix in", output)
        self.assertIn("No fallback SDK was used", output)
        self.assertIn("CwhipConfig.cmake", output)

    def test_missing_install_has_actionable_diagnostic(self):
        self.env.pop("CMAKE_PREFIX_PATH")
        output = self.configure(success=False, extra=[
            "-DCMAKE_DISABLE_FIND_PACKAGE_Cwhip=TRUE",
            "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
            "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
            "-DCMAKE_IGNORE_PREFIX_PATH=/usr;/usr/local;/opt",
        ])
        output = " ".join(output.split())
        self.assertIn("No SDK prefix was selected", output)
        self.assertIn('export CWHIP_SDK=', output)
        self.assertIn("install the SDK first", output)

    def test_lowercase_package_config_filename(self):
        selected = self.make_sdk("lowercase")
        package = selected / "lib/cmake/Cwhip"
        (package / "CwhipConfig.cmake").rename(package / "cwhip-config.cmake")
        (package / "CwhipConfigVersion.cmake").rename(
            package / "cwhip-config-version.cmake"
        )
        self.env["CWHIP_SDK"] = str(selected)
        self.assertEqual(self.configure(), str(selected))

    def test_empty_settings_falls_back_to_cmake_discovery(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))

    def test_invalid_legacy_setting_fails_instead_of_falling_back(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('sdk_prefix = "relative"\n')
        output = self.configure(success=False)
        self.assertIn("sdk_prefix", output)
        self.assertIn("settings.toml", output)

    def test_legacy_settings_used_when_sdk_file_is_absent(self):
        selected = self.make_sdk("legacy")
        self.select(selected, self.settings)
        self.assertEqual(self.configure(), str(selected))

    def test_sdk_settings_precede_legacy_settings(self):
        legacy = self.make_sdk("legacy")
        self.select(legacy, self.settings)
        selected = self.make_sdk("registered")
        self.select(selected)
        self.assertEqual(self.configure(), str(selected))

    def test_preferences_rewrite_does_not_change_registered_sdk(self):
        selected = self.make_sdk("dedicated")
        self.select(selected)
        rewritten_preferences_sdk = self.make_sdk("preferences rewrite")
        self.select(rewritten_preferences_sdk, self.settings)
        self.assertEqual(self.configure(), str(selected))

    def test_malformed_sdk_file_does_not_fall_back_to_legacy(self):
        legacy = self.make_sdk("legacy")
        self.select(legacy, self.settings)
        self.sdk_settings.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_settings.write_text("invalid = [\n")
        output = self.configure(success=False)
        self.assertIn("sdk.toml", output)
        self.assertIn("cannot read sdk_prefix", output)

    def test_empty_sdk_prefix_is_invalid(self):
        self.sdk_settings.parent.mkdir(parents=True)
        self.sdk_settings.write_text('sdk_prefix = ""\n')
        output = self.configure(success=False)
        self.assertIn("sdk.toml", output)
        self.assertIn("non-empty absolute path", output)

    def test_sdk_prefix_with_line_break_is_invalid(self):
        selected = self.make_sdk("registered\nprefix")
        self.select(selected)
        output = self.configure(success=False)
        self.assertIn("sdk.toml", output)
        self.assertIn("NUL or line breaks", output)

    def test_sdk_settings_directory_is_authoritative_error(self):
        legacy = self.make_sdk("legacy")
        self.select(legacy, self.settings)
        self.sdk_settings.mkdir(parents=True)
        output = self.configure(success=False)
        self.assertIn("sdk.toml", output)
        self.assertIn("cannot read sdk_prefix", output)

    def test_dangling_sdk_settings_symlink_is_authoritative_error(self):
        legacy = self.make_sdk("legacy")
        self.select(legacy, self.settings)
        self.sdk_settings.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_settings.symlink_to(self.root / "missing-sdk.toml")
        output = self.configure(success=False)
        self.assertIn("sdk.toml", output)
        self.assertIn("cannot read sdk_prefix", output)

    def test_xdg_sdk_settings_override_home_settings(self):
        home_sdk = self.make_sdk("home")
        self.select(home_sdk, self.sdk_settings)
        xdg = self.root / "xdg"
        xdg_settings = xdg / "cwhip/sdk.toml"
        xdg_settings.parent.mkdir(parents=True)
        xdg_sdk = self.make_sdk("xdg")
        xdg_settings.write_text(f"sdk_prefix = {json.dumps(str(xdg_sdk))}\n")
        self.env["XDG_CONFIG_HOME"] = str(xdg)
        self.assertEqual(self.configure(), str(xdg_sdk))

    def test_xdg_config_home_is_exclusive_of_home_config(self):
        home_sdk = self.make_sdk("home")
        self.select(home_sdk, self.sdk_settings)
        self.env["XDG_CONFIG_HOME"] = str(self.root / "empty-xdg")
        self.assertEqual(self.configure(), str(self.root / "fallback"))

    def test_relative_xdg_config_home_is_invalid(self):
        self.env["XDG_CONFIG_HOME"] = "relative"
        output = self.configure(success=False)
        self.assertIn("config home", output)
        self.assertIn("not absolute", output)

    def run_setup(self):
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
        return subprocess.run(
            ["/bin/bash", str(self.project / "scripts/setup")],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_setup_uses_registered_prefix_for_cmake_and_shell_path(self):
        prefix = self.make_sdk("registered SDK 'quoted'")
        self.select(prefix)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.build / "selected-sdk.txt").read_text(), str(prefix))
        self.assertEqual((self.root / "shell-path.txt").read_text().split(":")[:3], [
            str(self.project / "bin"),
            str(self.project / "scripts"),
            str(prefix / "bin"),
        ])

    def test_setup_explicit_sdk_bypasses_invalid_registration(self):
        self.sdk_settings.parent.mkdir(parents=True)
        self.sdk_settings.write_text("invalid = [\n")
        prefix = self.make_sdk("explicit SDK")
        self.env["CWHIP_SDK"] = str(prefix)
        self.env["XDG_CONFIG_HOME"] = "relative"
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.build / "selected-sdk.txt").read_text(), str(prefix))

    def test_setup_invalid_prefix_does_not_start_shell(self):
        self.env["CWHIP_SDK"] = str(self.home)
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CWHIP_SDK", result.stderr)
        self.assertIn("project shell was not started", result.stderr)
        self.assertFalse((self.root / "shell-path.txt").exists())

    def test_missing_settings_does_not_create_user_configuration(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertFalse(self.sdk_settings.exists())
        self.assertFalse(self.settings.exists())


class InstalledSdkTests(unittest.TestCase):
    def test_sdk_toml_builds_generator_and_examples_with_installed_sdk(self):
        prefix = os.environ.get("CWHIP_SDK")
        if not prefix:
            self.skipTest("set CWHIP_SDK to validate a real installed SDK")
        with tempfile.TemporaryDirectory(prefix="cparsegen SDK ") as directory:
            root = Path(directory)
            settings = root / "config/cwhip/sdk.toml"
            settings.parent.mkdir(parents=True)
            settings.write_text(f"sdk_prefix = {json.dumps(prefix)}\n")
            env = os.environ.copy()
            for name in ("CWHIP_SDK", "CMAKE_PREFIX_PATH", "Cwhip_DIR", "Cwhip_ROOT"):
                env.pop(name, None)
            home = root / "home"
            home.mkdir()
            env["HOME"] = str(home)
            env["XDG_CONFIG_HOME"] = str(root / "config")
            result = subprocess.run(
                ["cmake", "-S", str(ROOT), "-B", str(root / "build"),
                 f"-DCWHIP_BIN_DIR={root / 'bin'}",
                 f"-DCWHIP_LIB_DIR={root / 'lib'}"],
                env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"Using Cwhip SDK prefix: {prefix}", result.stdout)
            result = subprocess.run(
                ["cmake", "--build", str(root / "build"),
                 "--target", "calculator", "smallc", "--parallel", "4"],
                env=env, capture_output=True, text=True, timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((root / "bin/cparsegen").is_file())
            result = subprocess.run(
                [str(root / "bin/calculator"), "-e", "2 + 3 * 4"],
                env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout, "14\n")
            result = subprocess.run(
                [str(root / "bin/smallc-ast"),
                 str(ROOT / "examples/smallc/valid/functions.c")],
                env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["name"], "translationUnit")


if __name__ == "__main__":
    unittest.main()
