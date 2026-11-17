# Decisions

## 2026-11-17: VM-only development and commits

Decision: use `/home/krish/runbox/runbox` on the Arch Linux ARM VM as the
sole authoritative working checkout. Codex runs on macOS and operates via SSH.

Rationale: Linux behavior must be developed and checked on Linux; a single
editing checkout reduces divergence between machines.

Alternatives: parallel editing in both clones or file synchronization. These
add reconciliation work and can confuse source state with VM test results.

Consequences: commit only from the VM. Keep local macOS routing instructions
separate from the development workflow. Remote unavailability blocks project
work; never silently fall back to local project edits.

## 2026-11-17: CMake/Ninja for milestone 1

Decision: use CMake, Ninja, C++20, and out-of-tree `build/` output. Integrate
Python-driven tests through CTest when the test suite is introduced.

Rationale: installed tools support explicit compiler settings and repeatable
build/test commands without external runtime dependencies.

Alternatives: direct compiler commands or handwritten Makefiles are sufficient
for a smoke test, but become less convenient as fixtures and modules grow.

Consequences: commands remain planned until CMakeLists.txt and tests are added.
