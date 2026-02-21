import asyncio
from app import _manual_scan
from core.db import init_db

async def main():
    await init_db()
    res = await _manual_scan("0xb8c77482e45f1f44de1745f52c74426c631bdd52", "bsc")
    print(res)

asyncio.run(main())
