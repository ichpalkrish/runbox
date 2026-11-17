# Project status

## Current milestone

Environment setup complete. Milestone 1 (command execution) has not started.
No application source, build configuration, or project integration tests exist.

## Verified environment and checks

- Authoritative checkout: `krish@192.168.29.195:/home/krish/runbox/runbox`.
- Arch Linux ARM, aarch64; GCC, Clang, Python, CMake, Ninja, Make, GDB,
  clang-format, Git, and strace available.
- Temporary C++20 compilation and fork/exec/wait smoke test passed during the
  environment review; this is not a runlab implementation test.
- User/mount/network/PID namespace creation probe passed.
- `strace -qq -f /bin/true` passed after strace installation.
- Transient user service with `Delegate=yes` exposed cpu/memory/pids and
  successfully created/removed a child cgroup. Enforcement is not yet tested.
- Ignore rules, LF attributes, source trackability, and documentation whitespace
  checks passed. GitHub read access and fast-forward update succeeded.

## Limitations

Ordinary SSH sessions lack writable cgroups. Ptrace scope is 1. Seccomp policy,
resource enforcement, sandbox cleanup, fault injection, and runlab behavior are
unimplemented and unverified. Push access has not been tested. No milestone is
complete based on these environment probes.

## Next concrete action

The developer begins milestone 1: introduce a minimal C++20 command launcher
and build configuration, execute an argv without an implicit shell, wait, and
report normal/nonzero exit or terminating signal. Add distinct exec/setup
failure reporting and Python integration cases before completing the milestone.
