import logging
import asyncio
from conductor_client import ConductorPool

logging.basicConfig(level=logging.DEBUG)

async def main():
    pool = ConductorPool(
        ["ws://127.0.0.1:9001"],
        "d-cloud",
        "file_storage"
    )
    await pool.connect_all()
    print("Connected count:", pool.connected_count)

if __name__ == "__main__":
    asyncio.run(main())
