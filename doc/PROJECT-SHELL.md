# Project shell

Run `scripts/setup [debug|release|profile]` from any working directory to
configure this project and start its interactive Bash shell. The script
locates the project relative to itself, so it does not depend on the caller's
current directory. The default build type is `debug`.

The setup script configures before starting the shell. If configuration
fails, it reports the error and exits without opening a project shell.
Launching setup from an already initialized project shell is rejected to
avoid stacking project environments. Exiting the child Bash returns to the
shell from which setup was launched.

The project shell sources `~/.bashrc` when readable, adds the project's
`bin/` and `scripts/` directories to `PATH`, and starts in `build/`. If
`CWHIP_SDK` is set, its `bin/` directory is also added to `PATH` after the
project directories so the SDK compiler and package tools are available.

The shell exports:

| Variable | Meaning |
| --- | --- |
| `_PROJECT_NAME` | Project directory name |
| `_PROJECT_LOC` | Absolute project root |
| `_BUILD_TYPE` | Selected lowercase type: `debug`, `release`, or `profile` |
| `CWHIP_BUILD_TYPE` | Corresponding CMake type: `Debug`, `Release`, or `RelWithDebInfo` |

Convenience commands operate on the project repository:

| Command | Action |
| --- | --- |
| `status [args...]` | Run `git status` |
| `add [pathspec...]` | Stage the supplied pathspecs, or `.` when omitted |
| `commit [args...]` | Run `git commit` |
| `push [args...]` | Run `git push` |
| `all [commit args...]` | Explicitly stage all changes, commit, then push |
| `dbg [args...]` | Run `cdbg` with the supplied source or executable arguments |

These commands do not run automatically. In particular, entering the shell
does not stage, commit, or push changes.
