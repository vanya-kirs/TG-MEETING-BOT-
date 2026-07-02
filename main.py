import os
import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import ErrorEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot, Dispatcher
import asyncio
from dotenv import find_dotenv, load_dotenv

import faulthandler, signal

faulthandler.register(signal.SIGUSR1, all_threads=True)

load_dotenv(find_dotenv())

# Настройка логирования в файл
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
log_file = log_dir / 'bot.log'

# Создаем ротирующий файловый обработчик (макс 10MB, 5 файлов бэкапа)
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# Настраиваем корневой логгер
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Также выводим в консоль для systemd
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logging.getLogger().addHandler(console_handler)

from aiogram.enums import ParseMode
from handlers.admin_router import change_name1, notify_birthdays, yved_ikya_o_vstreche, sync_trainer_sheet_data, notify_trainer_expirations, admins
from handlers.group_router import group_router, process_scheduled_notifications, cleanup_payment_thread_messages, notify_dev_birthday
from handlers.admin_router import admin_router
from handlers.user_router import user_router

logger = logging.getLogger(__name__)

TOKEN = os.getenv('TOKEN')

_http_session = AiohttpSession()
_http_session._connector_init['enable_cleanup_closed'] = True
_http_session._connector_init['keepalive_timeout'] = 30

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=_http_session)

dp=Dispatcher()

dp.include_router(admin_router)
dp.include_router(group_router)
dp.include_router(user_router)


async def _notify_admins(text: str):
    try:
        await bot.send_message(916539100, text)
    except Exception:
        pass


@dp.errors()
async def handle_error(event: ErrorEvent):
    tb = ''.join(traceback.format_exception(type(event.exception), event.exception, event.exception.__traceback__))
    short_tb = tb[-3500:]
    update_info = f"update_id={event.update.update_id}" if event.update else "нет апдейта"
    text = f"❌ <b>Ошибка в обработчике</b> ({update_info}):\n<pre>{short_tb}</pre>"
    logger.error(f"Unhandled handler error: {event.exception}", exc_info=event.exception)
    await _notify_admins(text)


async def yvedomlenie(bot:Bot):
    mes=916539100
    await bot.send_message(mes, 'буй')


async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(change_name1, trigger='cron', hour=18, minute=00, kwargs={'bot':bot})
    scheduler.add_job(notify_birthdays, trigger='cron', hour=9, minute=0, kwargs={'bot': bot})
    scheduler.add_job(yved_ikya_o_vstreche, trigger='cron', hour=9, minute=00, kwargs={'bot': bot})
    scheduler.add_job(process_scheduled_notifications, trigger='interval', minutes=1, kwargs={'bot': bot})
    scheduler.add_job(cleanup_payment_thread_messages, trigger='cron', day=15, hour=12, minute=0, kwargs={'bot': bot})
    scheduler.add_job(sync_trainer_sheet_data, trigger='interval', minutes=10, kwargs={'bot': bot})
    scheduler.add_job(notify_trainer_expirations, trigger='cron', hour=9, minute=0, kwargs={'bot': bot})
    scheduler.add_job(notify_dev_birthday, trigger='cron', month=8, day=23, hour=9, minute=0, kwargs={'bot': bot})
    scheduler.start()
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), polling_timeout=25)
    except Exception as e:
        tb = traceback.format_exc()
        logger.critical(f"Bot crashed: {e}", exc_info=True)
        await _notify_admins(f"💀 <b>Бот упал</b>:\n<pre>{tb[-3500:]}</pre>")
        raise


asyncio.run(main())



