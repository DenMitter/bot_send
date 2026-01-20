from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.auth_flow import AuthFlowManager

logging.basicConfig(level=logging.DEBUG)


async def run(phone: str) -> None:
    manager = AuthFlowManager()
    try:
        await manager.start(1, phone)
        print("Запит виконано, очікуйте код")
    finally:
        await manager.cancel(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Відправити код авторизації")
    parser.add_argument("--phone", required=True, help="Номер телефону з +")
    args = parser.parse_args()
    asyncio.run(run(args.phone))
