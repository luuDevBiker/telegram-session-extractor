# Telegram Session Extractor

Tool desktop (PyQt6) trích xuất session Telegram Web từ Chrome profile + probe verify còn sống.

## Cài đặt

```bash
cd /home/pupubug/Documents/mycode/telegram-session-extractor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Chạy

### GUI (PyQt6)
```bash
.venv/bin/python gui.py
```

### CLI (test pipeline)
```bash
.venv/bin/python test_cli.py <zip_file_or_profile_dir>
```

## Chức năng

1. **Input**: chọn file ZIP hoặc thư mục Chrome profile
2. **Extract**: quét `Local Storage/leveldb` → session JSON (dcId, auth_key, phone, userId)
3. **Probe**: gọi Telegram `get_me()` concurrent để verify còn sống
4. **Output**:
   - File `.session` (Telethon format) ở `~/telegram_sessions/`
   - Excel metadata (phone, status, username, user_id, error)

## Ví dụ

```bash
# Test với zip file
.venv/bin/python test_cli.py /tmp/teledata/gpm_export_20261017_174215-20261019T023531Z-1-001.zip

# Kết quả:
# - 19 .session files (mỗi 28KB)
# - sessions.xlsx (6KB)
# - Hiển thị summary: alive/dead/error
```

## Import vào platform mmo

File `.session` xuất ra tương thích với Telethon, có thể import qua pipeline `session_import` của mmo:

```bash
# Copy session files vào container
docker cp ~/telegram_sessions/*.session mmo-telegram-backend:/tmp/sessions/

# Import (batch ≤32 files)
docker exec mmo-telegram-backend python -c "
import asyncio, pathlib
from telegram_app.config import get_settings
from telegram_app.services import session_import

async def main():
    s = get_settings()
    rep = await session_import.import_sessions(
        target_url=s.database_url,
        target_key=s.encryption_secret,
        session_dir=pathlib.Path('/tmp/sessions'),
        creds={'default': {'api_id': 611335, 'api_hash': 'd524b414d21f4d37f08684c1df41ac9c'}},
        apply=True,
        actor='cli:session-extractor',
    )
    print(f'Imported: {len(rep.items)} accounts')
asyncio.run(main())
"
```

## Cấu trúc project

- `extractor.py`: module extract Chrome profile (leveldb → session JSON)
- `probe.py`: module probe Telegram (Telethon get_me concurrent)
- `gui.py`: GUI PyQt6
- `test_cli.py`: CLI test pipeline
- `requirements.txt`: dependencies
