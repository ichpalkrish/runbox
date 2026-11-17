# Development workflow

## Source and execution locations

The authoritative Git checkout is `/Users/krishichpal/Documents/runbox` on
macOS. Edit source and documentation, inspect diffs, create commits, and push
from that checkout. The Arch Linux ARM VM at `krish@192.168.29.195` is the
execution host. Codex edits, builds, and runs tests in disposable snapshots at
`/home/krish/runbox-vm-workspaces/<session-id>/source`.

The former VM checkout at `/home/krish/runbox/runbox` is preserved for recovery
and is not a worktree for new tasks. Each session transfers one clean macOS
commit to a fresh VM directory. The VM returns a patch and recorded results;
there is no automatic or bidirectional file sync. The VM session has no Git
metadata, and no commits are made there.

## Start a session

1. Read `AGENTS.md`, this guide, `docs/PROJECT_STATUS.md`, and relevant
   decisions. Inspect `git status --short --branch`. Preserve unfinished work
   and start from a clean checkout.
2. Create or switch to the task branch on macOS. Start the session:

   ```sh
   python3 scripts/session.py start
   ```

   The command prints a session ID, local state directory, VM source path, and
   base commit. Its `manifest.json` also records the base. The default local state
   directory is `~/.cache/runbox-vm-sessions/<session-id>`. Use `--host`,
   `--remote-root`, or `--state-dir` only when needed.
3. Open the reported workspace in a tmux session on the VM. Replace the two
   uppercase placeholders with the values printed by `start`:

   ```sh
   ssh -t krish@192.168.29.195 \
     'tmux new-session -A -s SESSION_ID -c REMOTE_WORKSPACE'
   ```

   Detach with `Ctrl-B`, then `D`. SSH can disconnect while tmux keeps the
   workspace session running. Run the same command again to reattach.
4. Read the snapshot's `AGENTS.md` and project status before editing. Start
   Codex with the installed model and reasoning effort:

   ```sh
   ~/.local/bin/codex --model gpt-6-luna \
     -c 'model_reasoning_effort="xhigh"'
   ```

   Keep source edits, builds, tests, and execution inside the session workspace.
   Record actual commands, results, and limitations in the appropriate project
   documentation. Use `build/`, `runs/`, or `artifacts/` for generated output.

The snapshot excludes `.git` and ignored files. Session creation stops on
tracked `.env*` files and common credential-like paths. Symlinks and special
files are unsupported and cause a safe failure. Keep secrets outside the
project tree, and inspect the session manifest before work.

## Return and import work

1. Collect the VM changes and result record on macOS:

   ```sh
   python3 scripts/session.py collect SESSION_ID
   ```

   This writes `patch.diff` and transfer metadata to `result.json` in the
   session's local state directory and updates `manifest.json`. The patch
   preserves added and deleted files, binary content, and executable bits.
   Common secret-like paths are omitted from the returned patch.
2. Review `result.json`, `manifest.json`, and `patch.diff`. Confirm the base
   commit and every changed path. Read the returned `docs/PROJECT_STATUS.md`
   and other changed documentation for Linux commands, results, and limits;
   `result.json` records transfer metadata, not test evidence. The importer
   treats returned paths as untrusted input.
3. Apply only when the same macOS checkout is still clean at the recorded base:

   ```sh
   python3 scripts/session.py apply SESSION_ID
   ```

   The command verifies the repository root, exact base commit, clean worktree,
   patch hash, and path list, then runs `git apply --check` before applying the
   patch unstaged. If the base or local files changed, stop and review the
   mismatch; do not force the patch.
4. Review `git status`, `git diff --stat`, the full diff, and
   `git diff --check`. Commit intended paths on macOS with an imperative
   subject, for example `Implement command exit reporting`. Push from macOS
   after reviewing the upstream state; never force-push to resolve divergence.

Keep the remote workspace and local session state until the returned patch has
been reviewed, applied, and committed or deliberately rejected. The commands
do not delete either copy. Start a new VM session from the resulting clean Mac
commit for follow-up work.

## Build and test plan

When changing the session transport, run its fixture tests on macOS:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -v
```

The session workflow has also passed a disposable Git fixture round-trip over
SSH. It covered text and binary changes, deletion, executable mode, addition of
a file whose name contains a newline, ignored output exclusion, and retention
of an ignored-but-tracked baseline. The importer rejected a missing remote
root, and applying left the fixture changes unstaged. Tmux attach, detach, and
reconnect were verified separately. These checks validate session transport
only; they do not test runlab behavior.

C++20 and Python integration tests are settled. Use CMake with Ninja and
out-of-tree `build/` output when milestone 1 introduces the build system.
Planned commands (not executable project commands yet):

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
```

Wire Python integration tests into CTest when tests are introduced. No runlab
application source, CMakeLists.txt, or application suite exists yet.

## Later resource-control work

An ordinary SSH session cgroup is not writable. A verified delegation entry is:

```sh
systemd-run --user --wait --pipe --collect -p Delegate=yes COMMAND ARGUMENTS...
```

This exposes writable CPU, memory, and pids controllers. Validate workload
placement, actual limits, accounting, and cleanup in milestone 4. Keep the
supervisor outside the restricted workload; do not run all development as root.
