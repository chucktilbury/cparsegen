"""Exercise Cwhip SDK discovery through the real project CMake file."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from generator_support import c_compile_command


ROOT = Path(__file__).resolve().parents[1]


class SdkDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "src").mkdir()
        (self.project / "examples/visitor").mkdir(parents=True)
        shutil.copy2(ROOT / "examples/visitor/words.c", self.project / "examples/visitor")
        (self.project / "examples/compiler").mkdir()
        shutil.copy2(ROOT / "examples/compiler/compiler.c", self.project / "examples/compiler")
        shutil.copy2(ROOT / "examples/compiler/statements.c", self.project / "examples/compiler")
        shutil.copy2(ROOT / "CMakeLists.txt", self.project)
        shutil.copy2(ROOT / ".project_env", self.project)
        shutil.copy2(ROOT / "scripts/setup", self.project / "scripts")
        shutil.copy2(ROOT / "scripts/sdk-prefix.py", self.project / "scripts")
        (self.project / "src/main.cw").write_text("start {}\n")
        shutil.copy2(ROOT / "src/paths.c", self.project / "src")
        self.home = self.root / "home"
        self.home.mkdir()
        self.sdk_settings = self.home / ".config/cwhip/sdk.toml"
        self.settings = self.home / ".config/cwhip/settings.toml"
        self.build = self.project / "build"
        self.env = os.environ.copy()
        for name in ("CWHIP_SDK", "CMAKE_PREFIX_PATH", "Cwhip_DIR", "XDG_CONFIG_HOME"):
            self.env.pop(name, None)
        self.env.pop("CMAKE_INSTALL_PREFIX", None)
        self.env.pop("CMAKE_BUILD_TYPE", None)
        self.env["HOME"] = str(self.home)
        fallback_sdk = self.make_sdk("fallback")
        self.env["CMAKE_PREFIX_PATH"] = str(fallback_sdk)
        self.env["CPARSEGEN_TEST_REGISTERED_SDK_PREFIX"] = str(fallback_sdk)
        self.env["CPARSEGEN_TEST_APPLICATION_INSTALL_PREFIX"] = str(
            self.root / "sdk-application-prefix"
        )
        self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"] = "RelWithDebInfo"
        self.env.pop("DESTDIR", None)

    def make_sdk(self, name, sdk_abi="numeric-v2"):
        prefix = self.root / name
        package = prefix / "lib/cmake/Cwhip"
        package.mkdir(parents=True)
        config = (
            'get_filename_component(prefix "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)\n'
            'set(Cwhip_PREFIX "${prefix}")\n'
            'file(WRITE "${CMAKE_BINARY_DIR}/selected-sdk.txt" "${prefix}")\n'
        )
        if sdk_abi is not None:
            config += f'set(Cwhip_SDK_ABI "{sdk_abi}")\n'
        config += (
            'set(Cwhip_APPLICATION_OUTPUT_DIRECTORIES TRUE)\n'
            'include("${CMAKE_CURRENT_LIST_DIR}/CwhipApplicationDefaults.cmake")\n'
            'function(cwhip_add_program name)\n'
            '  add_custom_target("${name}")\n'
            '  set_target_properties("${name}" PROPERTIES CWHIP_EXECUTABLE "${CMAKE_BINARY_DIR}/app")\n'
            'endfunction()\n'
        )
        (package / "CwhipConfig.cmake").write_text(config)
        (package / "CwhipApplicationDefaults.cmake").write_text(
            "function(cwhip_apply_application_defaults)\n"
            '  get_filename_component(selected_prefix "${Cwhip_PREFIX}" REALPATH)\n'
            '  get_filename_component(registered_prefix "$ENV{CPARSEGEN_TEST_REGISTERED_SDK_PREFIX}" REALPATH)\n'
            "  if(NOT selected_prefix STREQUAL registered_prefix)\n"
            "    return()\n"
            "  endif()\n"
            "  get_property(install_prefix_cached CACHE CMAKE_INSTALL_PREFIX "
            "PROPERTY TYPE SET)\n"
            "  if(NOT install_prefix_cached)\n"
            '    if(NOT "$ENV{CMAKE_INSTALL_PREFIX}" STREQUAL "")\n'
            '      set(CMAKE_INSTALL_PREFIX "$ENV{CMAKE_INSTALL_PREFIX}" '
            "CACHE PATH \"Install path prefix\" FORCE)\n"
            "    else()\n"
            '      set(CMAKE_INSTALL_PREFIX "$ENV{CPARSEGEN_TEST_APPLICATION_INSTALL_PREFIX}" '
            "CACHE PATH \"Install path prefix\" FORCE)\n"
            "    endif()\n"
            "  endif()\n"
            "  get_property(build_type_cached CACHE CMAKE_BUILD_TYPE "
            "PROPERTY TYPE SET)\n"
            "  if(NOT build_type_cached AND NOT CMAKE_CONFIGURATION_TYPES AND "
            '(NOT DEFINED CMAKE_BUILD_TYPE OR CMAKE_BUILD_TYPE STREQUAL ""))\n'
            '    if(DEFINED ENV{CMAKE_BUILD_TYPE})\n'
            '      set(build_type_default "$ENV{CMAKE_BUILD_TYPE}")\n'
            "    else()\n"
            '      set(build_type_default "$ENV{CPARSEGEN_TEST_APPLICATION_BUILD_TYPE}")\n'
            "    endif()\n"
            '    set(CMAKE_BUILD_TYPE "${build_type_default}" '
            "CACHE STRING \"Build type\" FORCE)\n"
            "  endif()\n"
            "endfunction()\n"
        )
        (package / "CwhipConfigVersion.cmake").write_text(
            'set(PACKAGE_VERSION "0.0.2")\n'
            'set(PACKAGE_VERSION_COMPATIBLE TRUE)\n'
            'set(PACKAGE_VERSION_EXACT TRUE)\n'
        )
        return prefix

    def select(self, prefix, settings=None):
        settings = settings or self.sdk_settings
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(f"sdk_prefix = {json.dumps(str(prefix))}\n")
        if settings == self.sdk_settings:
            self.env["CPARSEGEN_TEST_REGISTERED_SDK_PREFIX"] = str(prefix)

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

    def cache_value(self, name):
        cache = (self.build / "CMakeCache.txt").read_text().splitlines()
        prefix = f"{name}:"
        for line in cache:
            if line.startswith(prefix):
                return line.split("=", 1)[1]
        self.fail(f"{name} is missing from CMakeCache.txt")

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

    def test_sdk_application_defaults_seed_install_prefix_and_build_type(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertEqual(
            self.cache_value("CMAKE_INSTALL_PREFIX"),
            self.env["CPARSEGEN_TEST_APPLICATION_INSTALL_PREFIX"],
        )
        self.assertEqual(
            self.cache_value("CMAKE_BUILD_TYPE"),
            self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"],
        )

    def test_sdk_numeric_abi_is_required(self):
        for name, sdk_abi in (("legacy-abi", "legacy"), ("missing-abi", None)):
            with self.subTest(sdk_abi=sdk_abi):
                self.env["CWHIP_SDK"] = str(self.make_sdk(name, sdk_abi))
                output = self.configure(success=False)
                self.assertIn("Cwhip SDK has ABI", output)
                self.assertIn("numeric-v2", output)
                self.env.pop("CWHIP_SDK")

    def test_explicit_cmake_settings_override_sdk_application_defaults(self):
        self.assertEqual(
            self.configure(extra=[
                f"-DCMAKE_INSTALL_PREFIX={self.root / 'explicit-prefix'}",
                "-DCMAKE_BUILD_TYPE=Release",
            ]),
            str(self.root / "fallback"),
        )
        self.assertEqual(
            self.cache_value("CMAKE_INSTALL_PREFIX"),
            str(self.root / "explicit-prefix"),
        )
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "Release")

    def test_explicit_empty_build_type_overrides_sdk_application_default(self):
        self.assertEqual(
            self.configure(extra=["-DCMAKE_BUILD_TYPE="]),
            str(self.root / "fallback"),
        )
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "")
        self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"] = "Release"
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "")

    def test_install_prefix_environment_overrides_sdk_application_default(self):
        selected_prefix = self.root / "environment-prefix"
        self.env["CMAKE_INSTALL_PREFIX"] = str(selected_prefix)
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertEqual(self.cache_value("CMAKE_INSTALL_PREFIX"), str(selected_prefix))

    def test_build_type_environment_overrides_sdk_application_default(self):
        self.env["CMAKE_BUILD_TYPE"] = "Release"
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "Release")

    def test_existing_cache_values_override_changed_sdk_application_defaults(self):
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        install_prefix = self.cache_value("CMAKE_INSTALL_PREFIX")
        build_type = self.cache_value("CMAKE_BUILD_TYPE")
        self.env["CPARSEGEN_TEST_APPLICATION_INSTALL_PREFIX"] = str(
            self.root / "changed-sdk-prefix"
        )
        self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"] = "Release"
        self.assertEqual(self.configure(), str(self.root / "fallback"))
        self.assertEqual(self.cache_value("CMAKE_INSTALL_PREFIX"), install_prefix)
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), build_type)

    def test_sdk_defaults_do_not_apply_when_registered_sdk_differs(self):
        selected = self.make_sdk("explicit")
        registered = self.make_sdk("registered")
        self.select(registered)
        self.env["CWHIP_SDK"] = str(selected)
        self.assertEqual(self.configure(), str(selected))
        self.assertNotEqual(
            self.cache_value("CMAKE_INSTALL_PREFIX"),
            self.env["CPARSEGEN_TEST_APPLICATION_INSTALL_PREFIX"],
        )
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "")

    def test_staged_application_install_does_not_modify_sdk_registration(self):
        selected = self.make_sdk("registered")
        self.sdk_settings.parent.mkdir(parents=True, exist_ok=True)
        registration = (
            f"sdk_prefix = {json.dumps(str(selected))}\n\n"
            "[applications]\n"
            f"install_prefix = {json.dumps(str(self.root / 'registered-app-prefix'))}\n"
            'build_type = "Debug"\n'
        )
        self.sdk_settings.write_text(registration)
        self.env["CPARSEGEN_TEST_REGISTERED_SDK_PREFIX"] = str(selected)
        self.env["CPARSEGEN_TEST_APPLICATION_INSTALL_PREFIX"] = str(
            self.root / "registered-app-prefix"
        )
        self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"] = "Debug"
        staging = self.root / "staging"
        self.env["DESTDIR"] = str(staging)
        self.assertEqual(self.configure(), str(selected))
        executable = self.build / "app"
        executable.write_text("test application\n")
        executable.chmod(0o755)
        result = subprocess.run(
            ["cmake", "--install", str(self.build)],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        staged_executable = (
            staging
            / str(self.root / "registered-app-prefix").lstrip("/")
            / "bin/app"
        )
        self.assertEqual(staged_executable.read_text(), "test application\n")
        self.assertEqual(self.sdk_settings.read_text(), registration)

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

    def test_legacy_sdk_without_application_defaults_has_actionable_diagnostic(self):
        selected = self.make_sdk("legacy SDK")
        package = selected / "lib/cmake/Cwhip"
        config = package / "CwhipConfig.cmake"
        config.write_text(config.read_text().replace(
            'include("${CMAKE_CURRENT_LIST_DIR}/CwhipApplicationDefaults.cmake")\n',
            "",
        ))
        (package / "CwhipApplicationDefaults.cmake").unlink()
        for selection in ("normal", "registered", "explicit"):
            with self.subTest(selection=selection):
                if selection == "normal":
                    self.env["CMAKE_PREFIX_PATH"] = str(selected)
                elif selection == "registered":
                    self.select(selected)
                else:
                    self.env["CWHIP_SDK"] = str(selected)
                output = " ".join(self.configure(success=False).split())
                self.assertIn(str(selected), output)
                self.assertIn("missing the application-defaults capability", output)
                self.assertIn("cwhip_apply_application_defaults", output)
                self.assertIn("Rebuild and reinstall the updated Cwhip SDK", output)
                self.assertIn("CwhipApplicationDefaults.cmake", output)
                self.assertIn("CWHIP_SDK", output)
                self.assertIn("No fallback SDK was used", output)
                self.assertIn("doc/BUILDING.md", output)
                self.assertNotIn("Unknown CMake command", output)
                self.assertEqual(
                    (self.build / "selected-sdk.txt").read_text(), str(selected)
                )

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

    def run_setup(self, *args):
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
            ["/bin/bash", str(self.project / "scripts/setup"), *args],
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
        self.assertEqual(
            self.cache_value("CMAKE_BUILD_TYPE"),
            self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"],
        )
        self.assertEqual((self.root / "shell-path.txt").read_text().split(":")[:3], [
            str(self.project / "bin"),
            str(self.project / "scripts"),
            str(prefix / "bin"),
        ])

    def test_setup_explicit_build_type_overrides_sdk_default(self):
        prefix = self.make_sdk("registered")
        self.select(prefix)
        self.assertEqual(
            self.configure(extra=["-DCMAKE_BUILD_TYPE=Debug"]),
            str(prefix),
        )
        result = self.run_setup("release")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "Release")

    def test_setup_without_mode_preserves_existing_build_type_cache(self):
        prefix = self.make_sdk("registered")
        self.select(prefix)
        self.assertEqual(
            self.configure(extra=["-DCMAKE_BUILD_TYPE=Release"]),
            str(prefix),
        )
        self.env["CPARSEGEN_TEST_APPLICATION_BUILD_TYPE"] = "Debug"
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.cache_value("CMAKE_BUILD_TYPE"), "Release")

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
            application_prefix = root / "application-prefix"
            registration = (
                f"sdk_prefix = {json.dumps(prefix)}\n\n"
                "[applications]\n"
                f"install_prefix = {json.dumps(str(application_prefix))}\n"
                'build_type = "Debug"\n'
            )
            settings.write_text(registration)
            env = os.environ.copy()
            for name in (
                "CWHIP_SDK", "CMAKE_PREFIX_PATH", "Cwhip_DIR", "Cwhip_ROOT",
                "CMAKE_INSTALL_PREFIX", "CMAKE_BUILD_TYPE",
            ):
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
            cache = (root / "build/CMakeCache.txt").read_text()
            self.assertIn(
                f"CMAKE_INSTALL_PREFIX:PATH={application_prefix}",
                cache,
            )
            self.assertIn("CMAKE_BUILD_TYPE:STRING=Debug", cache)

            environment_prefix = root / "environment-prefix"
            environment_env = env.copy()
            environment_env["CMAKE_INSTALL_PREFIX"] = str(environment_prefix)
            environment_build = root / "environment-prefix-build"
            result = subprocess.run(
                ["cmake", "-S", str(ROOT), "-B", str(environment_build),
                 f"-DCWHIP_BIN_DIR={root / 'environment-bin'}",
                 f"-DCWHIP_LIB_DIR={root / 'environment-lib'}"],
                env=environment_env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            environment_cache = (environment_build / "CMakeCache.txt").read_text()
            self.assertIn(
                f"CMAKE_INSTALL_PREFIX:PATH={environment_prefix}",
                environment_cache,
            )

            environment_build_type = root / "environment-build-type-build"
            build_type_env = env.copy()
            build_type_env["CMAKE_BUILD_TYPE"] = "Release"
            result = subprocess.run(
                ["cmake", "-S", str(ROOT), "-B", str(environment_build_type),
                 f"-DCWHIP_BIN_DIR={root / 'environment-type-bin'}",
                 f"-DCWHIP_LIB_DIR={root / 'environment-type-lib'}"],
                env=build_type_env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            build_type_cache = (
                environment_build_type / "CMakeCache.txt"
            ).read_text()
            self.assertIn("CMAKE_BUILD_TYPE:STRING=Release", build_type_cache)

            explicit_build = root / "explicit-empty-build"
            result = subprocess.run(
                ["cmake", "-S", str(ROOT), "-B", str(explicit_build),
                 f"-DCWHIP_BIN_DIR={root / 'explicit-bin'}",
                 f"-DCWHIP_LIB_DIR={root / 'explicit-lib'}",
                 f"-DCMAKE_INSTALL_PREFIX={root / 'explicit-prefix'}",
                 "-DCMAKE_BUILD_TYPE="],
                env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            explicit_cache = (explicit_build / "CMakeCache.txt").read_text()
            self.assertIn(
                f"CMAKE_INSTALL_PREFIX:PATH={root / 'explicit-prefix'}",
                explicit_cache,
            )
            self.assertIn("CMAKE_BUILD_TYPE:STRING=\n", explicit_cache)
            result = subprocess.run(
                ["cmake", "-S", str(ROOT), "-B", str(explicit_build),
                 f"-DCWHIP_BIN_DIR={root / 'explicit-bin'}",
                 f"-DCWHIP_LIB_DIR={root / 'explicit-lib'}"],
                env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            explicit_cache = (explicit_build / "CMakeCache.txt").read_text()
            self.assertIn("CMAKE_BUILD_TYPE:STRING=\n", explicit_cache)

            mismatch_xdg = root / "mismatch-xdg"
            mismatch_settings = mismatch_xdg / "cwhip/sdk.toml"
            mismatch_settings.parent.mkdir(parents=True)
            mismatch_settings.write_text(
                f"sdk_prefix = {json.dumps(str(root / 'other-sdk'))}\n\n"
                "[applications]\n"
                f"install_prefix = {json.dumps(str(root / 'wrong-app-prefix'))}\n"
                'build_type = "Debug"\n'
            )
            mismatch_env = env.copy()
            mismatch_env["CWHIP_SDK"] = prefix
            mismatch_env["XDG_CONFIG_HOME"] = str(mismatch_xdg)
            mismatch_build = root / "mismatch-build"
            result = subprocess.run(
                ["cmake", "-S", str(ROOT), "-B", str(mismatch_build),
                 f"-DCWHIP_BIN_DIR={root / 'mismatch-bin'}",
                 f"-DCWHIP_LIB_DIR={root / 'mismatch-lib'}"],
                env=mismatch_env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            mismatch_cache = (mismatch_build / "CMakeCache.txt").read_text()
            self.assertNotIn(
                f"CMAKE_INSTALL_PREFIX:PATH={root / 'wrong-app-prefix'}",
                mismatch_cache,
            )
            self.assertNotIn("CMAKE_BUILD_TYPE:STRING=Debug", mismatch_cache)
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
            staging = root / "staging"
            staged_env = env.copy()
            staged_env["DESTDIR"] = str(staging)
            result = subprocess.run(
                ["cmake", "--install", str(root / "build")],
                env=staged_env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            staged_executable = (
                staging / str(application_prefix).lstrip("/") / "bin/cparsegen"
            )
            self.assertEqual(
                staged_executable.read_bytes(),
                (root / "bin/cparsegen").read_bytes(),
            )
            self.assertEqual(settings.read_text(), registration)
            install = root / "install"
            result = subprocess.run(
                ["cmake", "--install", str(root / "build"), "--prefix", str(install)],
                env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = install / "bin/cparsegen"
            self.assertEqual(installed.read_bytes(), (root / "bin/cparsegen").read_bytes())
            parser = root / "installed-parser.c"
            result = subprocess.run(
                [str(installed), "--target", "c", str(ROOT / "tests/fixtures/shortest.cpg"),
                 str(parser)], env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(parser.is_file())
            self.assertFalse(parser.with_suffix(".dot").exists())
            executable = root / "installed-parser"
            result = subprocess.run(
                c_compile_command(parser, executable), env=env,
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = root / "input.txt"
            source.write_text("123+456")
            result = subprocess.run(
                [str(executable), "--complete", str(source)], env=env,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "sum(INTEGER(123), @literal0(+), INTEGER(456))\n", ""))
            cwhip_parser = root / "installed-parser.cw"
            result = subprocess.run(
                [str(installed), str(ROOT / "tests/fixtures/shortest.cpg"),
                 str(cwhip_parser)], env=env,
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            cwhip_executable = root / "installed-cwhip-parser"
            result = subprocess.run(
                [str(Path(prefix) / "bin/cwhip"), str(cwhip_parser),
                 "-o", str(cwhip_executable)], env=env,
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [str(cwhip_executable), "--complete", str(source)], env=env,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "sum(INTEGER(123), @literal0(+), INTEGER(456))\n", ""))


if __name__ == "__main__":
    unittest.main()
