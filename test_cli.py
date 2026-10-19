"""CLI test for full pipeline without GUI."""
import asyncio
import sys
from pathlib import Path

from extractor import extract_from_zip, extract_from_profile_dir
from probe import probe_sessions_concurrent, ProbeResult
from openpyxl import Workbook
from datetime import datetime


async def main():
    if len(sys.argv) < 2:
        print("Usage: test_cli.py <zip_file_or_profile_dir>")
        sys.exit(1)

    path = Path(sys.argv[1])
    output_dir = Path.home() / "telegram_sessions_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input: {path}")
    print(f"Output: {output_dir}")

    # Extract
    print("\n=== EXTRACTING ===")
    if path.is_file() and path.suffix == ".zip":
        sessions = extract_from_zip(path)
    elif path.is_dir():
        sess = extract_from_profile_dir(path)
        sessions = {"profile": sess} if sess else {}
    else:
        print("Invalid input: must be zip file or directory")
        sys.exit(1)

    print(f"Found {len(sessions)} sessions")

    if not sessions:
        print("No sessions found, exiting")
        sys.exit(0)

    # Probe
    print("\n=== PROBING ===")

    def progress(cur, total):
        print(f"Progress: {cur}/{total}", end="\r")

    results = await probe_sessions_concurrent(
        sessions,
        output_dir,
        progress_callback=progress,
    )
    print()  # newline after progress

    # Summary
    alive = sum(1 for r in results if r.status == "alive")
    dead = sum(1 for r in results if r.status == "dead")
    errors = sum(1 for r in results if r.status == "error")

    print(f"\n=== SUMMARY ===")
    print(f"Alive: {alive}")
    print(f"Dead: {dead}")
    print(f"Error: {errors}")

    # Export Excel
    print("\n=== EXPORTING EXCEL ===")
    wb = Workbook()
    ws = wb.active
    ws.title = "Telegram Sessions"

    headers = [
        "Phone", "Status", "User ID", "Username",
        "First Name", "Last Name", "Error", "Exported At"
    ]
    ws.append(headers)

    for r in results:
        ws.append([
            r.phone, r.status, r.user_id, r.username,
            r.first_name, r.last_name, r.error,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])

    excel_path = output_dir / "sessions.xlsx"
    wb.save(excel_path)
    print(f"Excel saved: {excel_path}")

    # List .session files
    print(f"\n=== SESSION FILES ===")
    session_files = list(output_dir.glob("*.session"))
    print(f"Generated {len(session_files)} .session files:")
    for f in session_files[:5]:
        print(f"  {f.name}")
    if len(session_files) > 5:
        print(f"  ... and {len(session_files) - 5} more")


if __name__ == "__main__":
    asyncio.run(main())
