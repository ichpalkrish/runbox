# Environment review

Reviewed on 2026-11-17 through SSH in `/home/krish/runbox/runbox`.

## Verified environment

- Authoritative checkout: `krish@192.168.29.195:/home/krish/runbox/runbox`.
- Arch Linux ARM; Linux `7.3.4-3-aarch64-ARCH`; native architecture `aarch64`.
- GCC 16.1.1, Python 3.14.10, CMake 4.5.0, Ninja 1.13.2 present.
  Clang, Make, Git, and pkg-config are also available.
- Temporary C++20 program compiled with warnings as errors and successfully
  executed `/bin/true` using fork/exec/wait. Temporary files were removed.
- Basic user namespace and combined user/mount/network/PID namespace creation
  succeeded. This does not verify a complete sandbox implementation.
- Cgroup v2 exposes memory, pids, cpu and other controllers. The current user
  cannot write its session cgroup; delegation/resource enforcement is unverified.
- Ptrace scope is 1. Seccomp is inactive for this session; installation and
  ptrace interactions remain untested.
- GitHub SSH read access succeeded; remote main matched local HEAD at
  `8d318bb644863e7583183998a6d2b7e3cfba9c61`. Push permission was not tested.

## Changes and validation

Added `.gitignore` for C++ builds, Python caches/environments, experiment output,
editor files, macOS metadata, and local environment configuration. Added
`.gitattributes` for LF text. Source and fixture paths remain trackable.
Representative ignore and attribute checks passed. Added Git workflow guidance
to `AGENTS.md`. Local settings: `pull.ff=only`, `push.default=simple`, and
`core.autocrlf=false`. These settings do not propagate to other clones.

## Finalized handoff

Git author is configured locally as `Krish Ichpal <krishichpal5@gmail.com>`.
The full project guide is now in VM `AGENTS.md`; macOS has routing guidance.
Strace 7.3 was installed and successfully traced `/bin/true`.
A transient `systemd-run --user --wait --pipe --collect -p Delegate=yes` service
exposed writable cpu/memory/pids controllers and created/removed a child cgroup.
Actual workload limits and seccomp remain unverified implementation work.

See `DEVELOPMENT.md` for the concrete session/commit workflow,
`PROJECT_STATUS.md` for current capability, and `DECISIONS.md` for choices.
The project has no application source or application test suite yet.
