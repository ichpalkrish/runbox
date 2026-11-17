# Repository Guidelines — Linux Execution Lab

## Source and execution environment

The authoritative Git checkout is `/Users/krishichpal/Documents/runbox` on
macOS. This guide is copied unchanged into VM snapshots, so its source-of-truth
rules always refer to that macOS path. The Linux execution VM is
`krish@192.168.29.195`; its disposable session workspaces live under
`/home/krish/runbox-vm-workspaces/`. Build, test, and run the project in those
Linux workspaces. The old `/home/krish/runbox/runbox` checkout is preserved for
recovery and is not an active project workspace.

On macOS, inspect Git status and start a clean-HEAD snapshot with
`python3 scripts/session.py start`. Attach to the reported VM workspace through
SSH and tmux. When working on the VM, edit only that session workspace. Collect
the return patch, review it, and apply it on macOS only when the local checkout
is still clean at the recorded base commit. See `docs/DEVELOPMENT.md` for exact
commands and limits.

There is no automatic synchronization between macOS and the VM. A session
starts from one frozen local commit; its reviewed patch returns to that same
checkout. Never commit in a VM session or edit the preserved legacy checkout.
Keep credentials outside project source. Session creation blocks `.env*` files
and common credential-like paths; review every returned manifest and patch.
Ignored build output stays out of snapshots, and remote workspaces remain until
the import is verified.

## Git workflow

Inspect `git status --short --branch` before work. Fetch with `git fetch origin`
and update only a clean branch with `git pull --ff-only`. If histories diverge,
inspect both sides and reconcile intentionally; do not force-push or discard
work to make synchronization pass. Use a focused feature branch for each
change, stage explicit paths, review staged and unstaged diffs, and commit on
macOS. Push from macOS after reviewing the diff and the current upstream state.
Keep builds, caches, and experiment output in ignored locations. Shared
`.gitattributes` normalizes text to LF. Never use an automatic "ours" merge rule
for project guidance or source; that can silently discard changes.


## Project identity and working style

Build `runlab`, an educational Linux execution sandbox for process tracing and fault injection. The settled choices are C++20, Linux, native VM architecture, CLI, Python integration tests, and small C/C++ fixtures. Names remain provisional. Do not reopen project/language selection or make large prerequisite-reading plans. Keep attention on the current milestone; explain mechanisms when relevant and distinguish proposals, implementation, and verified behavior. Give guidance or code to match the request rather than implementing the whole project automatically.

## Continuity and source of truth

At each coding session, read this file and nested `AGENTS.md` files, inspect repository changes and progress docs, then continue from the current milestone's next incomplete acceptance criterion. Code and executed checks establish what works; plans and docs do not.

When implementation begins, maintain `docs/PROJECT_STATUS.md` with the milestone, implemented capabilities, checks actually run and results, defects/limitations, environment constraints, and next action. Maintain `docs/DECISIONS.md` for consequential decisions, including rationale, alternatives, and consequences. Update these after meaningful changes; omit speculation and repetitive logs. Never claim unverified behavior or passing tests.

## Purpose and boundaries

The eventual tool launches and supervises a command and descendants, establishes selected isolation/resource limits, observes and records execution, applies explicit syscall restrictions, injects supported syscall failures, reports results, and cleans up. Example investigations include process/thread creation, syscall and file-open attempts, network attempts, denied operations, failed writes, resource limits, and surviving descendants.

This is a controlled investigation tool, not initially a machine-wide EDR, malware classifier, full debugger, complete container platform, deterministic record/replay system, production security boundary, or safe arbitrary-malware platform. Develop in a disposable Linux VM with controlled fixtures. State host/kernel assumptions and make security claims only when implementation and tests support them.

References to consult as needed: [NsJail](https://github.com/google/nsjail), [bubblewrap](https://github.com/containers/bubblewrap), [strace](https://github.com/strace/strace), [Firejail](https://github.com/netblue30/firejail), Linux man-pages, and kernel documentation for namespaces, cgroup v2, and seccomp. Check current docs when API, architecture, or kernel support matters; respect licenses. Reading whole projects/docs is not a prerequisite.

## Established approach and architecture

Use direct Linux APIs, RAII, ptrace for initial tracing, namespaces for selected isolation, cgroup v2 for workload-wide resource controls, seccomp for explicit syscall restrictions, and Python for integration tests. Details to decide when needed include process topology, CLI/config and event schemas, root filesystem, supported syscalls, fault-rule semantics, and privileged/delegated operation. Do not present proposals as implemented.

Keep responsibilities clear across CLI/config, supervisor, sandbox setup, resource controller, tracer, policy installer, fault engine, and reporter without forcing an early class hierarchy. The supervisor remains outside the restricted workload. Keep task identity, lifecycle, and resource ownership consistent.

## C++ and Linux engineering

- Prefer clear, small interfaces and explicit ownership. Use move-only RAII wrappers for owned descriptors; destructors do not throw. Provide explicit cleanup when failure must be reported.
- Check syscall results and preserve useful `errno`. Handle `EINTR` and partial I/O according to each operation; avoid blanket retries.
- Avoid owning raw pointers, scattered manual cleanup, elaborate inheritance/templates, and abstractions that hide lifecycle transitions. Add dependencies only for concrete benefit.
- Avoid unsafe work between `fork` and `exec` if the supervisor becomes multithreaded; revisit launch design before adding threads.
- Isolate architecture-specific syscall/register handling. Implement one native architecture first.

## Supervision and isolation

Launch with an argument vector; do not invoke a shell implicitly. Handle normal/nonzero exit, signal death, missing executable/exec failure, separate stdout/stderr, large concurrent output without deadlock, monotonic deadlines, interruption, descendants/reaping, and partial setup cleanup. Distinguish main-command exit, workload completion, pipe EOF, and cleanup completion. Descendants can retain pipes or escape process groups/sessions. Close unused pipe ends, use close-on-exec where appropriate, and consider pidfds. An exec-error pipe is a reasonable design proposal.

Define the filesystem root, read-only/writable paths, `/proc`, devices, mount propagation, and inherited descriptors. Use only needed mount/PID/network/user namespaces; consider credentials, capabilities, and `no_new_privs`. `chroot` alone is not a boundary. Verify UID/GID mapping and host support before claiming rootless operation. PID 1 must forward/handle signals and reap children. Never use setuid root as a shortcut. Requested isolation/setup failure must prevent an unrestricted launch.

Use cgroup v2 for supported workload-wide limits/accounting (memory, task count, optionally CPU); use rlimits where semantics fit. Distinguish wall timeout, CPU time, and CPU bandwidth. Check controller availability/delegation and place the workload before it executes. Do not infer OOM solely from `SIGKILL`; collect accounting evidence. Handle remaining tasks before cgroup cleanup.

## Tracing, policy, and fault injection

Track ptrace state per task. Handle syscall entry/exit, fork/clone/exec, task exit, signal and ptrace-event stops, restarted syscalls, and tasks disappearing. Trace syscall numbers/results and document a decoded subset; numeric tracing is not full argument decoding. Bound target-memory reads and tolerate failures. Paths observed at syscall entry are not authoritative filesystem provenance; relative paths, dirfds, symlinks, and races matter. Descriptor tracking must account for duplication, close, inheritance, and descriptor reuse.

Use seccomp for explicit restrictions and account for syscall ABI/architecture. Seccomp is not a complete sandbox, and classic filters cannot dereference pathname pointers. Do not claim scalar filters enforce pathname policy. Trace-derived allowlists do not prove completeness; runtime libraries need syscalls. Define denial outcomes, test ptrace/seccomp interactions, and prevent execution if policy installation fails. Start with a manually understood policy.

Initial injection is selected syscall-error substitution for controlled single-threaded workloads: detect entry, match a documented rule, suppress the operation before side effects, set the configured error, and record the intervention. Never execute the operation and merely falsify its result. Verify architecture-specific suppression/result setting. Define syscall, occurrence, counting scope, activation point, errno, injection count, and task scope. Avoid counting loader/startup calls unintentionally. Example `--fault write:5:ENOSPC` is illustrative until semantics are defined. Defer arbitrary successful-return substitution, general short-I/O/allocation simulation, and deterministic multithreaded injection.

## Reporting and tests

JSON summary and JSON Lines events are suggestions; schemas remain undecided. Record relevant command/config/environment/kernel/architecture, enabled/unsupported features, event sequence and monotonic time, task/process events, observations/interventions/policy outcomes, resource evidence, target status, timeout, setup/tracer/cleanup errors, and output truncation/gaps. Separate facts from inferences. Bound output and supervisor memory; report truncation/spooling. Repeated experiments are not deterministic replay.

Use Python integration tests and focused C/C++ fixtures. Test failure paths as well as happy paths and keep expected outcomes explicit. Compare traces with `strace` and isolation with established tools; investigate differences rather than treating references as infallible. Measure plain execution, supervision, isolation/resource controls, tracing, injection enabled without match, and actual injection separately. Repeat and report kernel, architecture, VM resources, build, and workload. Use sanitizers/debuggers when useful and account for ptrace/limit interactions. Distinguish target bugs, harness defects, and runlab defects.

## Milestones and finish line

1. **Command execution:** launch, wait, report exit/signal; cover success, nonzero, missing executable, signal, and distinct supervisor/setup failures.
2. **Reliable supervision:** capture output, deadlines, interruption, cleanup; cover concurrent large output, hangs, descendants retaining pipes, interruption, partial failure, bounded output.
3. **Tracing:** task tracking and selected syscalls; cover known calls, fork/exec, signals, per-task entry/exit, unsupported decoding.
4. **Isolation/resources:** restricted filesystem, disabled networking, limits; verify intended access, unavailable paths, inherited descriptors, pre-exec setup, and cleanup.
5. **Policy:** small explicit policy; allowed/denied behavior and setup failure.
6. **Fault injection:** defined occurrence, suppressed side effect, observed errno, baseline comparison, recorded intervention.
7. **Evaluation/docs:** real workloads, correctness, overhead, and limitations.

Version one additionally needs machine-readable events and summary, cleanup after exit/crash/timeout/setup failure, integration coverage, and documented support boundaries/overhead. Tracing descendants may precede multi-task injection; document them separately. A happy path alone never completes a milestone.

## Deferred scope

Before version one, defer general record/replay, deterministic multithreaded injection, checkpoint/restore, cross-architecture support, full syscall decoding, GUI/web, Docker management/full OCI, machine-wide EDR, integrated fuzzing, eBPF backend, source debugger, and production malware-containment claims. Do not make these prerequisites.

## Repository organization

Adapt to the repository; do not create empty scaffolding or overwrite existing conventions. Suggested paths: `src/`, optional `include/`, `tests/`, `docs/PROJECT_STATUS.md`, `docs/DECISIONS.md`, other focused `docs/`, `README.md`, and this guide. Record actual build/test commands in the README when selected.

## Current handoff and next action

Environment preparation is complete for milestone 1 on native aarch64 Linux.
No runlab source or application tests exist yet. Read `docs/PROJECT_STATUS.md`
for verified checks and the next acceptance criterion; read
`docs/DEVELOPMENT.md` for the session and commit workflow.
