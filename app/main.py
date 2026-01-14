import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import accounts, admin, mailing, user
from app.client.telethon_manager import TelethonManager
from app.core.config import get_settings
from app.core.logger import setup_logging
from app.db.init import init_db
from app.db.session import get_engine, get_session_factory
from app.services.mailing.runner import MailingRunner
from app.services.web_auth_server import WebAuthServer


async def run_mailing_worker() -> None:
    session_factory = get_session_factory()
    manager = TelethonManager()
    async with session_factory() as session:
        runner = MailingRunner(session, manager)
        await runner.run_forever()


async def main() -> None:
    setup_logging()
    settings = get_settings()

    await init_db(get_engine())

    web_server = WebAuthServer(settings.web_auth_host, settings.web_auth_port)
    web_server.start()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(user.router)
    dp.include_router(accounts.router)
    dp.include_router(admin.router)
    dp.include_router(mailing.router)

    asyncio.create_task(run_mailing_worker())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
