# Development workflow

## Where work happens

Run Codex on macOS and use SSH for every project operation:

```sh
ssh krish@192.168.29.195
cd /home/krish/runbox/runbox
```

The VM is the sole editing, build, test, and commit checkout. A remote editor
connected to this directory is also suitable. The macOS directory is a Codex
entry point with routing instructions; do not develop or commit there. Do not
synchronize working files using scp/rsync or copy `.git` between machines.
The full project guide is `AGENTS.md` in this VM checkout.

## Each session

1. Read `AGENTS.md`, applicable nested guides, `docs/PROJECT_STATUS.md`, and
   relevant decisions. Inspect `git status --short --branch` and `git diff`.
2. Preserve unfinished work. When clean, run `git fetch origin`, switch to
   `main`, and run `git pull --ff-only`. If histories diverge, inspect them
   before choosing a resolution. Never force push to synchronize clones.
3. Create a focused branch: `git switch -c milestone-1/command-launch`.
   Resume the existing branch when continuing unfinished work.
4. Work on the next incomplete acceptance criterion. The developer implements
   and learns; Codex provides explanations, reviews, hints, or code as requested.
5. Build and check on the VM. Keep generated files in `build/`, `runs/`, or
   `artifacts/`. Record commands actually run, outcomes, and remaining limits.
6. Update progress and consequential decisions. Review `git diff` and
   `git diff --check`, stage explicit intended paths, review
   `git diff --cached`, and commit from this VM only.
7. Push the branch from the VM when requested or authorized:
   `git push -u origin HEAD`. Review/merge through the repository's normal
   GitHub workflow, then fast-forward VM main before the next branch.

Use imperative commit subjects, e.g. `Implement command exit reporting`.
Local Git identity: `Krish Ichpal <krishichpal5@gmail.com>`. Pulls require
fast-forward history; pushes use `simple`; text uses LF. Changes to these local
Git settings do not propagate to another clone. `.gitignore` prevents generated
noise, not conflicts in tracked files. Resolve real conflicts deliberately.
Do not configure an automatic "ours" merge driver.

## Build and test plan

C++20 and Python integration tests are settled. Use CMake with Ninja and
out-of-tree `build/` output when milestone 1 introduces the build system.
Planned commands (not executable project commands yet):

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
```

Wire Python integration tests into CTest when tests are introduced. No source,
CMakeLists.txt, or application suite exists at environment handoff.

## Later resource-control work

The ordinary SSH session cgroup is not writable. A verified delegation entry is:

```sh
systemd-run --user --wait --pipe --collect -p Delegate=yes COMMAND ARGUMENTS...
```

This exposes writable CPU, memory, and pids controllers. Validate workload
placement, actual limits, accounting, and cleanup in milestone 4. Keep the
supervisor outside the restricted workload; do not run all development as root.
