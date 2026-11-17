# Project status

## Current milestone

Environment setup complete. Milestone 1 (command execution) has not started.
No application source, build configuration, or project integration tests exist.

## Verified environment and checks

- Authoritative Git checkout: `/Users/krishichpal/Documents/runbox` on macOS.
- Arch Linux ARM execution VM: `krish@192.168.29.195`, native aarch64; source
  snapshots run under `/home/krish/runbox-vm-workspaces/`.
- GCC, Clang, Python, CMake, Ninja, Make, GDB, clang-format, Git, and strace
  are available on the VM.
- Codex CLI 0.169.0 for Linux ARM64 is installed and signed in using ChatGPT.
  An explicit read-only CLI request with `gpt-6-luna` and xhigh reasoning
  returned `READY`; the CLI reported the requested model and effort.
- tmux 3.8 is installed for persistent VM work across SSH disconnects.
- The former VM checkout is preserved and archived at
  `/home/krish/runbox/migration-backup-20261117/original-runbox.tar.gz`.
- Temporary C++20 compilation and fork/exec/wait smoke test passed during the
  environment review; this is not a runlab implementation test.
- User/mount/network/PID namespace creation probe passed.
- `strace -qq -f /bin/true` passed after strace installation.
- Transient user service with `Delegate=yes` exposed cpu/memory/pids and
  successfully created/removed a child cgroup. Enforcement is not yet tested.
- Ignore rules, LF attributes, source trackability, and documentation
  whitespace checks passed. The unpublished VM setup commit and README edit
  were recovered to macOS without altering the original VM checkout.
- Six session-tool fixture tests and an SSH fixture round-trip passed; the
  round-trip verified text, binary, deletion, file-mode, and a file whose name
  contains a newline, plus ignored-output filtering, baseline preservation, and
  unstaged import.
  Tmux attach/detach/reconnect also passed. These checks do not exercise runlab.

## Limitations

Ordinary SSH sessions lack writable cgroups. Ptrace scope is 1. Seccomp policy,
resource enforcement, sandbox cleanup, fault injection, and runlab behavior are
unimplemented and unverified. The model smoke check does not verify unrelated
Codex features or broader model availability. No milestone is complete based
on these environment probes.

## Next concrete action

Start milestone 1 from a clean Mac commit with `python3 scripts/session.py
start`. In the resulting Linux workspace, introduce a minimal C++20 command
launcher and build configuration, execute an argv without an implicit shell,
wait, and report normal/nonzero exit or terminating signal. Add distinct
exec/setup failure reporting and Python integration cases before completing
the milestone. Return the reviewed patch and commit it from macOS.
