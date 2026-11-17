# Linux Execution Lab

Linux Execution Lab is an educational C++20 command-line tool for running a
workload under supervision, tracing selected system calls, applying isolation
and resource limits, and injecting controlled syscall failures. Its provisional
executable name is `runlab`.

The authoritative Git checkout is `/Users/krishichpal/Documents/runbox` on
macOS. Codex works in disposable Linux VM snapshots at
`krish@192.168.29.195`; build, test, and run the project there. See [the
development workflow](docs/DEVELOPMENT.md) for starting a session and reviewing
its returned patch.

## Project status

Environment setup is complete. The application implementation has not started;
there are no application build or test commands yet. The first milestone is to
launch an argument-vector command, wait for it, and report its exit status or
terminating signal. See [current status](docs/PROJECT_STATUS.md) and the full
[contributor guide](AGENTS.md).

## Planned capabilities

The first version is planned to provide:

- Supervision of a command and its descendants, including output capture,
  deadlines, and cleanup.
- Selected filesystem, network, and resource isolation using Linux facilities.
- ptrace-based process and syscall observation with a documented decoding
  subset.
- Explicit seccomp syscall restrictions.
- Controlled syscall-error injection for selected single-threaded workloads.
- Machine-readable event records and a run summary.

These are project goals, not claims about implemented or verified behavior.
The tool is intended for controlled experiments in a disposable Linux VM; it
is not a production security boundary.

## Development prerequisites

The target is native Linux architecture; current development is on aarch64.
The VM has GCC, CMake, Ninja, Python, strace, tmux, and Codex CLI available.
Exact build and test commands will be added when milestone 1 introduces the
build system.

See [environment checks](docs/ENVIRONMENT.md) and [design decisions](docs/DECISIONS.md).
