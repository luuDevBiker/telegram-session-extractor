"""Probe Telegram sessions to verify they are alive."""
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from telethon.crypto import AuthKey

DC_ADDRS = {
    1: "149.154.175.53",
    2: "149.154.167.51",
    3: "149.154.175.100",
    4: "149.154.167.91",
    5: "91.108.56.130",
}
# Telegram Web K public API
API_ID = 611335
API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


@dataclass
class ProbeResult:
    phone: str
    status: str  # "alive", "dead", "error"
    user_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    error: Optional[str] = None


async def probe_session(session_json: dict, session_file: Path) -> ProbeResult:
    """Probe a single session JSON and create .session file."""
    dc = session_json["dcId"]
    key = session_json.get(f"dc{dc}_auth_key")
    if not key:
        return ProbeResult(
            phone=f"+{session_json.get('phone', '?')}",
            status="error",
            error="missing_auth_key"
        )

    # Create SQLite session
    s = SQLiteSession(str(session_file))
    s.set_dc(dc, DC_ADDRS[dc], 443)
    s.auth_key = AuthKey(bytes.fromhex(key))
    s.save()

    client = TelegramClient(
        s,
        api_id=API_ID,
        api_hash=API_HASH,
        timeout=15,
        connection_retries=1,
        retry_delay=0,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            return ProbeResult(
                phone=f"+{session_json.get('phone', '?')}",
                status="dead",
                error="unauthorized"
            )

        me = await client.get_me()
        return ProbeResult(
            phone=f"+{me.phone}",
            status="alive",
            user_id=me.id,
            username=me.username,
            first_name=me.first_name,
            last_name=me.last_name,
        )
    except Exception as e:
        return ProbeResult(
            phone=f"+{session_json.get('phone', '?')}",
            status="error",
            error=f"{type(e).__name__}: {e}"
        )
    finally:
        await client.disconnect()


async def probe_sessions_concurrent(
    sessions: dict[str, dict],
    output_dir: Path,
    max_concurrent: int = 6,
    progress_callback=None,
) -> list[ProbeResult]:
    """Probe multiple sessions concurrently.

    Args:
        sessions: mapping profile_id → session JSON
        output_dir: directory to save .session files
        max_concurrent: max parallel probes
        progress_callback: callable(current, total) for UI updates

    Returns:
        List of ProbeResult
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(max_concurrent)
    results = []

    async def guarded(profile_id: str, sess: dict):
        async with sem:
            session_file = output_dir / f"+{sess['phone']}.session"
            result = await probe_session(sess, session_file)
            results.append(result)
            if progress_callback:
                progress_callback(len(results), len(sessions))
            return result

    tasks = [guarded(pid, sess) for pid, sess in sessions.items()]
    await asyncio.gather(*tasks)

    return results


async def main():
    """CLI test."""
    import sys
    import json
    from extractor import extract_from_zip

    if len(sys.argv) < 2:
        print("Usage: probe.py <zip_file>")
        sys.exit(1)

    zip_path = Path(sys.argv[1])
    sessions = extract_from_zip(zip_path)
    print(f"Extracted {len(sessions)} sessions, probing...")

    def progress(cur, total):
        print(f"Progress: {cur}/{total}")

    results = await probe_sessions_concurrent(
        sessions,
        Path("/tmp/tg_sessions_probe"),
        progress_callback=progress,
    )

    alive = sum(1 for r in results if r.status == "alive")
    print(f"\nAlive: {alive}/{len(results)}")
    for r in results:
        if r.status == "alive":
            print(f"  {r.phone} {r.first_name} {r.last_name or ''} @{r.username or ''}")
        else:
            print(f"  {r.phone} {r.status}: {r.error}")


if __name__ == "__main__":
    asyncio.run(main())
