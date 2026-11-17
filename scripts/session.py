#!/usr/bin/env python3
"""Move a disposable VM source workspace to and from the Mac-owned checkout.

The VM receives source files only. It never receives Git metadata, and this
script generates the return patch locally with a temporary Git index.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Sequence


DEFAULT_HOST = os.environ.get("RUNBOX_VM_HOST", "krish@192.168.29.195")
DEFAULT_REMOTE_ROOT = "/home/krish/runbox-vm-workspaces"
DEFAULT_STATE_DIR = Path.home() / ".cache" / "runbox-vm-sessions"
FORMAT_VERSION = 1


class SessionError(RuntimeError):
    """A user-facing workflow error."""


def run_git(repo: Path, *args: str, env: dict[str, str] | None = None,
            input_data: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, input=input_data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
    )


def git_output(repo: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
    return run_git(repo, *args, env=env).stdout


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    output = run_git(current, "rev-parse", "--show-toplevel")
    return Path(os.fsdecode(output.stdout.rstrip(b"\n"))).resolve()


def current_head(repo: Path) -> str:
    return git_output(repo, "rev-parse", "HEAD").decode("ascii").strip()


def assert_clean_checkout(repo: Path) -> None:
    status = git_output(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        preview = status.decode("utf-8", errors="replace").strip().splitlines()
        details = "\n".join(f"  {line}" for line in preview[:12])
        if len(preview) > 12:
            details += f"\n  ... and {len(preview) - 12} more"
        raise SessionError("the Mac checkout must be clean before this operation:\n" + details)


def git_paths(repo: Path, base: str) -> list[str]:
    raw = git_output(repo, "ls-tree", "-r", "-z", "--name-only", base)
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def path_parts(path: str) -> tuple[str, ...]:
    if "\0" in path:
        raise SessionError("a file path contains a NUL byte")
    posix_path = PurePosixPath(path)
    if posix_path.is_absolute() or not posix_path.parts:
        raise SessionError(f"unsafe path in source workspace: {path!r}")
    if any(part in ("", ".", "..") for part in posix_path.parts):
        raise SessionError(f"unsafe path in source workspace: {path!r}")
    if any(part == ".git" for part in posix_path.parts):
        raise SessionError("Git metadata is not allowed in a source workspace")
    return posix_path.parts


def is_sensitive_path(path: str) -> bool:
    """Recognize common credential/config paths that must never be exported."""
    parts = tuple(part.casefold() for part in path_parts(path))
    name = parts[-1]
    if any(part in {".aws", ".ssh", "secrets", "secret", "credentials"} for part in parts):
        return True
    if any(part == ".env" or part.startswith(".env.") for part in parts):
        return True
    if name in {"id_rsa", "id_ed25519", "known_hosts", "credentials.json", "service-account.json"}:
        return True
    return name.endswith((".pem", ".key", ".p12", ".pfx", ".jks"))


def validate_host(host: str) -> str:
    if host.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_.@:-]+", host):
        raise SessionError("SSH host must be a host alias, user@host, or address")
    return host


def validate_remote_root(root: str) -> str:
    p = PurePosixPath(root)
    if not p.is_absolute() or ".." in p.parts or root == "/":
        raise SessionError("remote root must be an absolute directory without '..'")
    normalized = posixpath.normpath(root)
    protected = PurePosixPath("/home/krish/runbox/runbox")
    candidate = PurePosixPath(normalized)
    if candidate == protected or protected in candidate.parents:
        raise SessionError("remote workspaces must stay outside /home/krish/runbox/runbox")
    return normalized


def create_scratch_index(repo: Path, base: str, scratch: Path, index_path: Path,
                         git_dir: Path | None = None) -> dict[str, str]:
    """Materialize BASE into SCRATCH using an isolated temporary Git index."""
    actual_git_dir = git_dir or Path(git_output(repo, "rev-parse", "--absolute-git-dir").decode().strip())
    env = os.environ.copy()
    env.update({
        "GIT_DIR": str(actual_git_dir),
        "GIT_WORK_TREE": str(scratch),
        "GIT_INDEX_FILE": str(index_path),
    })
    scratch.mkdir(parents=True, exist_ok=True)
    run_git(repo, "read-tree", base, env=env)
    run_git(repo, "checkout-index", "--all", "--force", env=env)
    return env


def check_ignored(repo: Path, paths: Sequence[str]) -> set[str]:
    if not paths:
        return set()
    payload = b"\0".join(os.fsencode(path) for path in paths) + b"\0"
    result = run_git(repo, "check-ignore", "--no-index", "-z", "--stdin", check=False,
                     input_data=payload)
    if result.returncode not in (0, 1):
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise SessionError(f"could not check ignore rules: {message}")
    return {os.fsdecode(item) for item in result.stdout.split(b"\0") if item}


def write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_manifest(session_dir: Path) -> dict:
    path = session_dir / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SessionError(f"missing or invalid session manifest: {path}") from exc
    if manifest.get("format_version") != FORMAT_VERSION:
        raise SessionError("unsupported session manifest version")
    return manifest


def session_directory(state_dir: Path, session_id: str) -> Path:
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", session_id):
        raise SessionError("invalid session ID")
    root = state_dir.expanduser().resolve()
    path = root / session_id
    if path.parent != root:
        raise SessionError("invalid session path")
    return path


def add_snapshot_tree(repo: Path, base: str, snapshot: Path,
                      paths: Sequence[str]) -> None:
    temp_index = snapshot.parent / "snapshot.index"
    env = create_scratch_index(repo, base, snapshot, temp_index)
    # The index may contain ignored tracked files; source export deliberately
    # limits itself to the paths selected below.
    for path in paths:
        path_parts(path)
        source = snapshot.joinpath(*PurePosixPath(path).parts)
        if source.is_symlink():
            raise SessionError(f"symlink is not supported in the source workspace: {path!r}")
        if not source.is_file():
            raise SessionError(f"tracked path is not a regular file: {path!r}")
    # Files are already materialized from BASE. Remove paths outside the export
    # set, deepest first, so no ignored/generated content reaches the VM.
    exported = set(paths)
    all_paths = git_paths(repo, base)
    for path in sorted((p for p in all_paths if p not in exported),
                       key=lambda item: len(PurePosixPath(item).parts), reverse=True):
        target = snapshot.joinpath(*PurePosixPath(path).parts)
        if target.is_dir() and not target.is_symlink():
            continue
        target.unlink(missing_ok=True)
    # Drop empty directories left behind by filtered paths.
    for directory, subdirs, files in os.walk(snapshot, topdown=False):
        del subdirs, files
        candidate = Path(directory)
        if candidate != snapshot:
            try:
                candidate.rmdir()
            except OSError:
                pass
    # Keep temporary Git metadata local to the session, never inside snapshot.
    try:
        temp_index.unlink()
    except FileNotFoundError:
        pass
    del env


def pack_snapshot(snapshot: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT) as archive:
        for current, dirs, files in os.walk(snapshot, followlinks=False):
            dirs.sort()
            files.sort()
            for name in files:
                source = Path(current) / name
                relative = source.relative_to(snapshot).as_posix()
                info = source.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise SessionError(f"unsupported file type in snapshot: {relative!r}")
                archive.add(source, arcname=relative, recursive=False)


def start_session(repo: Path, state_dir: Path, host: str,
                  remote_root: str) -> tuple[str, Path]:
    assert_clean_checkout(repo)
    base = current_head(repo)
    paths = git_paths(repo, base)
    sensitive = sorted(path for path in paths if is_sensitive_path(path))
    if sensitive:
        preview = "\n".join(f"  {path!r}" for path in sensitive[:10])
        raise SessionError("tracked credential-like paths must be removed before export:\n" + preview)
    ignored = check_ignored(repo, paths)
    exported_paths = sorted(path for path in paths if path not in ignored)
    session_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = session_directory(state_dir, session_id)
    directory.mkdir(parents=True, exist_ok=False)
    snapshot = directory / "snapshot"
    snapshot.mkdir()
    add_snapshot_tree(repo, base, snapshot, exported_paths)
    archive_path = directory / "source.tar"
    pack_snapshot(snapshot, archive_path)

    host = validate_host(host)
    remote_root = validate_remote_root(remote_root)
    remote_session = posixpath.join(remote_root, session_id)
    remote_source = posixpath.join(remote_session, "source")
    remote_cmd = (
        f"mkdir -p {shlex.quote(remote_root)} && "
        f"mkdir {shlex.quote(remote_session)} && "
        f"mkdir {shlex.quote(remote_source)} && "
        f"tar -xf - -C {shlex.quote(remote_source)}"
    )
    try:
        with archive_path.open("rb") as source_tar:
            subprocess.run(["ssh", "-T", host, remote_cmd], stdin=source_tar, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        # Retain the local snapshot and archive for diagnosis/retry.
        raise SessionError(f"could not create remote workspace: {exc}") from exc

    manifest = {
        "format_version": FORMAT_VERSION,
        "session_id": session_id,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_root": str(repo),
        "base_commit": base,
        "host": host,
        "remote_root": remote_root,
        "remote_session": remote_session,
        "remote_source": remote_source,
        "exported_paths": exported_paths,
        "ignored_tracked_paths": sorted(ignored),
        "status": "started",
    }
    write_manifest(directory / "manifest.json", manifest)
    return session_id, directory


REMOTE_LIST_SCRIPT = r'''import os, sys
root = os.path.realpath(sys.argv[1])
if not os.path.isdir(root):
    sys.stderr.write("remote source workspace does not exist or is not a directory\n")
    sys.exit(2)
def fail(error):
    raise error
for current, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=fail):
    next_dirs = []
    symlink_dirs = []
    for name in sorted(dirs):
        if name == ".git":
            continue
        full = os.path.join(current, name)
        if os.path.islink(full):
            symlink_dirs.append(name)
        else:
            next_dirs.append(name)
    dirs[:] = next_dirs
    names = sorted(files + symlink_dirs)
    for name in names:
        if name == ".git":
            continue
        rel = os.path.relpath(os.path.join(current, name), root)
        sys.stdout.buffer.write(os.fsencode(rel) + b"\0")
'''


def remote_file_list(host: str, remote_source: str) -> list[str]:
    command = f"python3 -c {shlex.quote(REMOTE_LIST_SCRIPT)} {shlex.quote(remote_source)}"
    try:
        result = subprocess.run(["ssh", "-T", host, command], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        message = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            message = exc.stderr.decode("utf-8", errors="replace").strip()
        raise SessionError(f"could not list remote workspace: {message or exc}") from exc
    raw_paths = result.stdout.split(b"\0")
    if raw_paths and raw_paths[-1] == b"":
        raw_paths.pop()
    paths = [os.fsdecode(item) for item in raw_paths]
    for path in paths:
        path_parts(path)
    if len(paths) != len(set(paths)):
        raise SessionError("remote workspace listing contains duplicate paths")
    return paths


def select_return_paths(repo: Path, manifest: dict, remote_paths: Sequence[str]) -> list[str]:
    baseline = set(manifest["exported_paths"])
    all_base_paths = set(git_paths(repo, manifest["base_commit"]))
    candidates: list[str] = []
    for path in remote_paths:
        path_parts(path)
        if is_sensitive_path(path):
            continue
        if path in baseline:
            candidates.append(path)
            continue
        # Never return an ignored tracked path, even if the VM recreated it.
        if path in all_base_paths:
            continue
        candidates.append(path)
    ignored = check_ignored(repo, [path for path in candidates if path not in baseline])
    selected = [path for path in candidates if path in baseline or path not in ignored]
    # A new path cannot be placed under a baseline file or a filtered secret.
    selected_set = set(selected)
    for path in selected:
        parts = PurePosixPath(path).parts
        for index in range(1, len(parts)):
            parent = PurePosixPath(*parts[:index]).as_posix()
            if parent in all_base_paths and parent not in baseline:
                raise SessionError(f"new file {path!r} conflicts with a path excluded from the VM snapshot")
            if parent in selected_set:
                raise SessionError(f"remote workspace has a file and a child path at {parent!r}")
    return sorted(selected)


def download_selected_files(host: str, remote_source: str, paths: Sequence[str],
                           archive_path: Path) -> None:
    file_list = b"".join(b"./" + os.fsencode(path) + b"\0" for path in paths)
    command = (
        f"cd {shlex.quote(remote_source)} && "
        "tar --hard-dereference -cf - --null --files-from=-"
    )
    try:
        with archive_path.open("wb") as output:
            subprocess.run(["ssh", "-T", host, command], input=file_list,
                           stdout=output, stderr=subprocess.PIPE, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        message = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            message = exc.stderr.decode("utf-8", errors="replace").strip()
        raise SessionError(f"could not download remote source files: {message or exc}") from exc


def safe_extract_regular_tar(archive_path: Path, destination: Path,
                             expected_paths: set[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive:
            raw_name = member.name
            while raw_name.startswith("./"):
                raw_name = raw_name[2:]
            if not raw_name or raw_name == ".":
                continue
            parts = path_parts(raw_name)
            relative = PurePosixPath(*parts).as_posix()
            if relative not in expected_paths:
                raise SessionError(f"archive contains an unrequested path: {relative!r}")
            if relative in seen:
                raise SessionError(f"archive contains a duplicate path: {relative!r}")
            seen.add(relative)
            if not member.isfile():
                kind = "symlink" if member.issym() or member.islnk() else "special file"
                raise SessionError(f"{kind} is not supported in the source workspace: {relative!r}")
            if member.mode & (stat.S_ISUID | stat.S_ISGID):
                raise SessionError(f"setuid/setgid mode is not supported: {relative!r}")
            target = destination.joinpath(*parts)
            ensure_safe_directory(destination, target.parent)
            if target.exists() or target.is_symlink():
                raise SessionError(f"archive path already exists: {relative!r}")
            stream = archive.extractfile(member)
            if stream is None:
                raise SessionError(f"could not read archive path: {relative!r}")
            mode = 0o755 if member.mode & 0o111 else 0o644
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target, flags, mode)
            with os.fdopen(descriptor, "wb") as output, stream:
                shutil.copyfileobj(stream, output)
            os.chmod(target, mode, follow_symlinks=False)
    missing = expected_paths - seen
    if missing:
        raise SessionError("archive omitted requested paths: " + ", ".join(repr(p) for p in sorted(missing)[:8]))


def ensure_safe_directory(root: Path, target: Path) -> None:
    relative = target.relative_to(root)
    current = root
    for component in relative.parts:
        current = current / component
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise SessionError(f"archive parent is not a directory: {current}")
        else:
            current.mkdir(mode=0o755)


def remove_exported_baseline_paths(scratch: Path, paths: Sequence[str]) -> None:
    for path in sorted(paths, key=lambda item: len(PurePosixPath(item).parts), reverse=True):
        target = scratch.joinpath(*path_parts(path))
        if target.is_dir() and not target.is_symlink():
            # Git trees cannot have a file and descendants at the same path;
            # directories here are only structural parents of another path.
            continue
        target.unlink(missing_ok=True)
    for directory, dirs, files in os.walk(scratch, topdown=False):
        del dirs, files
        candidate = Path(directory)
        if candidate != scratch:
            try:
                candidate.rmdir()
            except OSError:
                pass


def overlay_return_tree(scratch: Path, returned: Path, returned_paths: Sequence[str]) -> None:
    for path in returned_paths:
        parts = path_parts(path)
        source = returned.joinpath(*parts)
        target = scratch.joinpath(*parts)
        ensure_safe_directory(scratch, target.parent)
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        source_mode = stat.S_IMODE(source.stat().st_mode)
        os.chmod(target, 0o755 if source_mode & 0o111 else 0o644)


def generate_patch(repo: Path, base: str, scratch: Path, session_dir: Path) -> tuple[bytes, list[str]]:
    actual_git_dir = Path(git_output(repo, "rev-parse", "--absolute-git-dir").decode().strip()).resolve()
    objects_dir = Path(git_output(repo, "rev-parse", "--git-path", "objects").decode().strip())
    if not objects_dir.is_absolute():
        objects_dir = repo / objects_dir
    objects_dir = objects_dir.resolve()
    if "\n" in str(objects_dir):
        raise SessionError("Git object path contains a newline and cannot be used safely")
    private_git = session_dir / "patch-objects.git"
    if private_git.exists():
        raise SessionError("private patch workspace already exists; refusing to overwrite it")
    run_git(repo, "init", "--bare", "--quiet", str(private_git))
    alternates = private_git / "objects" / "info" / "alternates"
    alternates.write_text(str(objects_dir) + "\n", encoding="utf-8")
    index_file = session_dir / "patch.index"
    env = os.environ.copy()
    env.update({
        "GIT_DIR": str(private_git),
        "GIT_WORK_TREE": str(scratch),
        "GIT_INDEX_FILE": str(index_file),
    })
    run_git(repo, "read-tree", base, env=env)
    run_git(repo, "add", "-A", "--", ".", env=env)
    changed = git_output(repo, "diff", "--cached", "--name-only", "-z", base, env=env)
    changed_paths = [os.fsdecode(item) for item in changed.split(b"\0") if item]
    for path in changed_paths:
        path_parts(path)
        if is_sensitive_path(path):
            raise SessionError(f"refusing to create a patch for a credential-like path: {path!r}")
    patch = git_output(repo, "diff", "--cached", "--binary", "--full-index", base, env=env)
    return patch, changed_paths


def collect_session(repo: Path, state_dir: Path, session_id: str,
                    host_override: str | None = None) -> Path:
    assert_clean_checkout(repo)
    directory = session_directory(state_dir, session_id)
    manifest = read_manifest(directory)
    if Path(manifest["repo_root"]).resolve() != repo.resolve():
        raise SessionError("session was started from a different checkout")
    if current_head(repo) != manifest["base_commit"]:
        raise SessionError("Mac checkout HEAD differs from the session base")
    if manifest.get("status") != "started":
        raise SessionError(f"session cannot be collected from status {manifest.get('status')!r}")
    host = validate_host(host_override or manifest["host"])
    remote_paths = remote_file_list(host, manifest["remote_source"])
    returned_paths = select_return_paths(repo, manifest, remote_paths)
    archive_path = directory / "return.tar"
    download_selected_files(host, manifest["remote_source"], returned_paths, archive_path)
    downloaded = directory / "returned"
    downloaded.mkdir(exist_ok=False)
    safe_extract_regular_tar(archive_path, downloaded, set(returned_paths))

    scratch = directory / "patch-tree"
    scratch.mkdir(exist_ok=False)
    index_path = directory / "tree.index"
    env = create_scratch_index(repo, manifest["base_commit"], scratch, index_path)
    del env
    remove_exported_baseline_paths(scratch, manifest["exported_paths"])
    overlay_return_tree(scratch, downloaded, returned_paths)
    patch, changed_paths = generate_patch(repo, manifest["base_commit"], scratch, directory)
    patch_path = directory / "patch.diff"
    if patch_path.exists() or (directory / "result.json").exists():
        raise SessionError("patch already collected; inspect or move it before collecting again")
    patch_path.write_bytes(patch)
    result = {
        "format_version": FORMAT_VERSION,
        "session_id": session_id,
        "base_commit": manifest["base_commit"],
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "changed_paths": changed_paths,
        "returned_file_count": len(returned_paths),
        "changed_path_count": len(changed_paths),
        "collected_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_manifest(directory / "result.json", result)
    manifest["status"] = "collected"
    manifest["host"] = host
    write_manifest(directory / "manifest.json", manifest)
    return directory


def verify_patch_paths(repo: Path, base: str, changed_paths: Sequence[str],
                       exported_paths: Sequence[str]) -> None:
    base_paths = set(git_paths(repo, base))
    exported = set(exported_paths)
    for path in changed_paths:
        parts = path_parts(path)
        if is_sensitive_path(path):
            raise SessionError(f"patch mentions a credential-like path: {path!r}")
        if path not in exported and path in base_paths:
            raise SessionError(f"patch changes a path excluded from the source snapshot: {path!r}")
        if path not in exported and path not in base_paths and path in check_ignored(repo, [path]):
            raise SessionError(f"patch adds an ignored generated path: {path!r}")
        # No path component may refer to the repository's Git metadata.
        if any(part == ".git" for part in parts):
            raise SessionError("patch may not modify Git metadata")


def apply_session(repo: Path, state_dir: Path, session_id: str) -> list[str]:
    directory = session_directory(state_dir, session_id)
    manifest = read_manifest(directory)
    if Path(manifest["repo_root"]).resolve() != repo.resolve():
        raise SessionError("session was started from a different checkout")
    if current_head(repo) != manifest["base_commit"]:
        raise SessionError("Mac checkout HEAD differs from the session base")
    assert_clean_checkout(repo)
    result_path = directory / "result.json"
    patch_path = directory / "patch.diff"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        patch = patch_path.read_bytes()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SessionError("collect the session before applying it") from exc
    if result.get("session_id") != session_id or result.get("base_commit") != manifest["base_commit"]:
        raise SessionError("result metadata does not match this session/base")
    patch_hash = hashlib.sha256(patch).hexdigest()
    if patch_hash != result.get("patch_sha256"):
        raise SessionError("patch hash differs from the collected result; collect again before applying")
    changed_paths = result.get("changed_paths")
    if not isinstance(changed_paths, list) or not all(isinstance(path, str) for path in changed_paths):
        raise SessionError("result metadata has an invalid changed path list")
    verify_patch_paths(repo, manifest["base_commit"], changed_paths, manifest["exported_paths"])
    if not patch:
        manifest["status"] = "applied"
        write_manifest(directory / "manifest.json", manifest)
        return []
    try:
        subprocess.run(["git", "apply", "--check", "--binary", str(patch_path)], cwd=repo, check=True)
        subprocess.run(["git", "apply", "--binary", str(patch_path)], cwd=repo, check=True)
    except subprocess.CalledProcessError as exc:
        raise SessionError(f"git apply rejected the patch: {exc}") from exc
    manifest["status"] = "applied"
    manifest["applied_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_manifest(directory / "manifest.json", manifest)
    return changed_paths


def state_directory(value: str | None) -> Path:
    return (Path(value).expanduser() if value else DEFAULT_STATE_DIR).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="send a clean committed snapshot to a fresh VM workspace")
    start.add_argument("--host", default=DEFAULT_HOST, help=f"SSH host (default: {DEFAULT_HOST})")
    start.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    start.add_argument("--state-dir", help=f"local session state directory (default: {DEFAULT_STATE_DIR})")

    collect = subparsers.add_parser("collect", help="download VM edits and create a binary patch")
    collect.add_argument("session_id")
    collect.add_argument("--host", help="override the SSH host saved by start")
    collect.add_argument("--state-dir", help=f"local session state directory (default: {DEFAULT_STATE_DIR})")

    apply = subparsers.add_parser("apply", help="apply a collected patch to the clean matching checkout")
    apply.add_argument("session_id")
    apply.add_argument("--state-dir", help=f"local session state directory (default: {DEFAULT_STATE_DIR})")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = repo_root()
        state_dir = state_directory(args.state_dir)
        if args.command == "start":
            session_id, directory = start_session(
                repo, state_dir, args.host, args.remote_root,
            )
            print(f"Session: {session_id}")
            print(f"Local state: {directory}")
            print(f"Base commit: {read_manifest(directory)['base_commit']}")
            print(f"VM workspace: {read_manifest(directory)['remote_source']}")
            print("The VM workspace has no Git metadata; review and collect edits before applying.")
            return 0
        if args.command == "collect":
            directory = collect_session(repo, state_dir, args.session_id, args.host)
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            print(f"Patch: {directory / 'patch.diff'}")
            print(f"Manifest: {directory / 'result.json'}")
            print(f"Changed paths: {result['changed_path_count']}")
            return 0
        changed = apply_session(repo, state_dir, args.session_id)
        print(f"Applied {len(changed)} changed path(s) to the working tree; nothing was committed.")
        for path in changed:
            print(f"  {path!r}")
        return 0
    except SessionError as exc:
        print(f"session: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f"session: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
