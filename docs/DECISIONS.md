# Decisions

## 2026-11-17: VM-only development and commits (superseded)

Decision: use `/home/krish/runbox/runbox` on the Arch Linux ARM VM as the
sole authoritative working checkout. Codex runs on macOS and operates via SSH.

Rationale: Linux behavior must be developed and checked on Linux; a single
editing checkout reduces divergence between machines.

Alternatives: parallel editing in both clones or file synchronization. These
add reconciliation work and can confuse source state with VM test results.

This decision was superseded on 2026-11-17 by the Mac-authoritative workflow
below. It records the previous setup and is not the current procedure.

## 2026-11-17: Mac source with disposable Linux workspaces

Decision: keep `/Users/krishichpal/Documents/runbox` on macOS as the only
authoritative source and Git checkout. Codex edits, builds, and runs checks in
fresh Linux VM workspaces created from a clean Mac commit. Return work as a
reviewed patch and apply it on macOS only when the checkout is clean at the
recorded base. Make all commits and pushes from macOS.

Rationale: source history stays under one Git authority while Linux behavior
continues to be developed and verified on the native Arch Linux ARM VM.

Alternatives: keep the VM checkout authoritative or synchronize two mutable
working trees automatically. The former conflicts with the developer's new
workflow; the latter makes source state and test results hard to reconcile.

Consequences: session workspaces contain no `.git`, are isolated under
`/home/krish/runbox-vm-workspaces/`, and remain until returned work is
verified. Snapshot creation requires a clean Mac worktree and records its
base commit. The importer rejects a changed base or dirty checkout. There is
no automatic sync; start a new VM session from the next clean Mac commit.
Use tmux to keep VM work available across SSH disconnects.

## 2026-11-17: CMake/Ninja for milestone 1

Decision: use CMake, Ninja, C++20, and out-of-tree `build/` output. Integrate
Python-driven tests through CTest when the test suite is introduced.

Rationale: installed tools support explicit compiler settings and repeatable
build/test commands without external runtime dependencies.

Alternatives: direct compiler commands or handwritten Makefiles are sufficient
for a smoke test, but become less convenient as fixtures and modules grow.

Consequences: commands remain planned until CMakeLists.txt and tests are added.
