"""Canonical hashing and atomic artifact helpers."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from pydantic import BaseModel

from harbor.publisher.packager import Packager
from harbor.skills import compute_skill_digest

EXCLUDED_NAMES = {".git", "__pycache__", ".DS_Store"}

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical_json(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", by_alias=True)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())

def sha256_tree(root: Path) -> str:
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file() and not EXCLUDED_NAMES.intersection(p.relative_to(root).parts))
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def git_object_sha1(kind: str, payload: bytes) -> str:
    header = f"{kind} {len(payload)}\0".encode()
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def git_tree_sha1(root: Path) -> str:
    """Reconstruct a Git tree object ID from a metadata-free snapshot."""
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")

    def tree(directory: Path) -> str:
        entries: list[tuple[bytes, bytes]] = []
        for path in directory.iterdir():
            if path.name in EXCLUDED_NAMES:
                continue
            name = path.name.encode("utf-8")
            if path.is_symlink():
                mode = b"120000"
                object_id = git_object_sha1("blob", os.readlink(path).encode("utf-8"))
                sort_key = name
            elif path.is_dir():
                mode = b"40000"
                object_id = tree(path)
                sort_key = name + b"/"
            elif path.is_file():
                mode = b"100755" if stat.S_IMODE(path.stat().st_mode) & 0o111 else b"100644"
                object_id = git_object_sha1("blob", path.read_bytes())
                sort_key = name
            else:
                raise ValueError(f"unsupported Git snapshot entry: {path}")
            entries.append((sort_key, mode + b" " + name + b"\0" + bytes.fromhex(object_id)))
        payload = b"".join(value for _, value in sorted(entries, key=lambda item: item[0]))
        return git_object_sha1("tree", payload)

    return tree(root)

def harbor_content_sha256(root: Path, *, virtual_files: dict[str, Path] | None = None) -> str:
    """Return Harbor v0.21's canonical directory content digest."""
    if not virtual_files:
        digest, _ = Packager.compute_content_hash(root)
        return digest
    files = Packager.collect_files(root)
    hashes = {
        path.relative_to(root).as_posix(): Packager.compute_file_hash(path)
        for path in files
    }
    for relative, source in virtual_files.items():
        if relative in hashes:
            if hashes[relative] != sha256_file(source):
                raise ValueError(f"virtual file disagrees with materialized task: {relative}")
        else:
            hashes[relative] = sha256_file(source)
    digest = hashlib.sha256()
    for relative, file_hash in sorted(hashes.items()):
        digest.update(f"{relative}\0{file_hash}\n".encode())
    return digest.hexdigest()


def harbor_skill_sha256(root: Path) -> str:
    """Return Harbor v0.21's canonical skill digest without the algorithm prefix."""
    return compute_skill_digest(root).removeprefix("sha256:")

def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)

def atomic_write_json(path: Path, value: object) -> None:
    atomic_write(path, canonical_json(value))
