# Environment review

Reviewed on 2026-11-17 during the Mac-authoritative workflow migration.

## Source and execution machines

- Authoritative Git checkout: `/Users/krishichpal/Documents/runbox` on macOS.
- Linux execution VM: `krish@192.168.29.195`, Arch Linux ARM, native
  `aarch64`, kernel `7.3.4-3-aarch64-ARCH`.
- Disposable session workspaces: `/home/krish/runbox-vm-workspaces/`.
- The former VM checkout at `/home/krish/runbox/runbox` is preserved for
  recovery. A full archive is at
  `/home/krish/runbox/migration-backup-20261117/original-runbox.tar.gz`.
- `tmux 3.8` is installed on the VM for sessions that must survive SSH
  disconnects.
- Codex CLI `0.169.0` standalone ARM64 build is installed and signed in using
  ChatGPT. A one-shot read-only request explicitly selected `gpt-6-luna` with
  `model_reasoning_effort=xhigh`; the CLI reported both settings and returned
  `READY`.

## Verified Linux facilities

- GCC 16.1.1, Python 3.14.10, CMake 4.5.0, Ninja 1.13.2, Clang, Make, Git,
  pkg-config, GDB, clang-format, and strace are available.
- A temporary C++20 program compiled with warnings as errors and successfully
  executed `/bin/true` using fork/exec/wait. Temporary files were removed.
- Basic user namespace and combined user/mount/network/PID namespace creation
  succeeded. This does not verify a complete sandbox implementation.
- Cgroup v2 exposes memory, pids, cpu and other controllers. An ordinary SSH
  session cannot write its session cgroup. A transient delegated user service
  exposed writable cpu/memory/pids controllers and created/removed a child
  cgroup; workload enforcement remains unverified.
- `strace -qq -f /bin/true` passed. Ptrace scope is 1; seccomp installation
  and ptrace interactions remain untested.
- The original VM Git checkout had one unpublished setup commit and an
  unstaged README edit. Both were recovered to the macOS checkout without
  changing that original checkout.

## Workflow validation

- Six session-tool fixture tests passed with
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -v`.
- An SSH round-trip against a disposable Git fixture transferred text and
  binary changes, deletion, executable mode, and a file whose name contains a
  newline. It excluded ignored output, retained an ignored-but-tracked baseline,
  rejected a missing remote root, and left the imported changes unstaged.
- A tmux attach/detach/reconnect smoke check passed. These are workflow checks,
  not runlab application tests.

## Workflow limits

Snapshots start from a clean macOS commit and contain no Git metadata. The
session tools block tracked `.env*` files and common credential-like paths;
keep credentials outside project source and inspect manifests and returned
patches. Symlinks and special files are unsupported. Build output and ignored
files are excluded. The importer requires the exact recorded base and a clean
macOS checkout, then applies changes unstaged for review. There is no automatic
sync or VM-side commit.

The exact model check proves that this signed-in CLI/account combination can
make a read-only request with Luna at xhigh. It does not verify unrelated Codex
features or broader model availability.

See `DEVELOPMENT.md` for the session commands, `PROJECT_STATUS.md` for project
capability, and `DECISIONS.md` for workflow rationale.
