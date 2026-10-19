"""Extract Telegram Web sessions from Chrome profiles.

Chrome profile structure:
  <profile>/Default/Local Storage/leveldb/*.log + *.ldb
  → JSON with dcId, dc{N}_auth_key, userId, phone
"""
import json
import re
import zipfile
from pathlib import Path
from typing import Iterator


SESSION_PATTERN = re.compile(rb'\{[^{}]*"dcId"[^{}]*\}')
DC_ADDRS = {
    1: "149.154.175.53",
    2: "149.154.167.51",
    3: "149.154.175.100",
    4: "149.154.167.91",
    5: "91.108.56.130",
}


def find_leveldb_dirs(root: Path) -> Iterator[Path]:
    """Yield paths to Local Storage leveldb directories."""
    for ldb_dir in sorted(root.rglob("leveldb")):
        if "Local Storage" in str(ldb_dir):
            yield ldb_dir


def extract_session_from_leveldb(ldb_dir: Path) -> dict | None:
    """Extract session JSON from leveldb files. Returns dict or None."""
    blob = b""
    for f in sorted(ldb_dir.iterdir()):
        if f.suffix in (".log", ".ldb"):
            blob += f.read_bytes()

    best = None
    for m in SESSION_PATTERN.finditer(blob):
        try:
            obj = json.loads(m.group().decode("utf8", "ignore"))
        except Exception:
            continue
        if "userId" not in obj:
            continue
        if not any(k.startswith("dc") and k.endswith("auth_key") for k in obj):
            continue
        if best is None or len(m.group()) > len(json.dumps(best).encode()):
            best = obj
    return best


def extract_from_profile_dir(profile_dir: Path) -> dict | None:
    """Extract session from a single Chrome profile directory."""
    for ldb_dir in find_leveldb_dirs(profile_dir):
        sess = extract_session_from_leveldb(ldb_dir)
        if sess:
            return sess
    return None


def extract_from_zip(zip_path: Path) -> dict[str, dict]:
    """Extract sessions from a zip file containing Chrome profiles.

    Returns mapping: profile_id → session dict
    """
    import tempfile

    result = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Extract only leveldb files to save space
            for name in zf.namelist():
                if "Local Storage/leveldb" in name and name.endswith((".log", ".ldb")):
                    zf.extract(name, tmp)

        for ldb_dir in find_leveldb_dirs(tmp):
            # Relative path from tmpdir: e.g. gpm_export_xxx/UUID/Default/Local Storage/leveldb
            rel = ldb_dir.relative_to(tmp)
            parts = rel.parts
            if len(parts) >= 3 and parts[1]:
                profile_uuid = parts[1]  # Second part is UUID
                sess = extract_session_from_leveldb(ldb_dir)
                if sess:
                    result[profile_uuid] = sess

    return result


def main():
    """CLI test."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: extractor.py <profile_dir_or_zip>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if path.is_dir():
        sess = extract_from_profile_dir(path)
        if sess:
            print(json.dumps(sess, indent=2))
        else:
            print("No session found")
    elif path.is_file() and path.suffix == ".zip":
        sessions = extract_from_zip(path)
        print(f"Found {len(sessions)} sessions")
        for uuid, sess in sessions.items():
            print(f"\n{uuid}:")
            print(f"  phone: +{sess.get('phone')}")
            print(f"  userId: {sess.get('userId')}")
            print(f"  dcId: {sess.get('dcId')}")


if __name__ == "__main__":
    main()
