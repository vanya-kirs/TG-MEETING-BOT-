import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram.client.default import DefaultBotProperties
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
from handlers.admin_router import change_name1, notify_birthdays, yved_ikya_o_vstreche, sync_trainer_sheet_data, notify_trainer_expirations
from handlers.group_router import group_router, process_scheduled_notifications, cleanup_payment_thread_messages, notify_dev_birthday
from handlers.admin_router import admin_router
from handlers.user_router import user_router


TOKEN = os.getenv('TOKEN')

bot=Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

dp=Dispatcher()

dp.include_router(admin_router)
dp.include_router(group_router)
dp.include_router(user_router)


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
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())




asyncio.run(main())



