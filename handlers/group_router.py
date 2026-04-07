from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, date, time, timedelta
import calendar
import logging
import asyncio

from database.client import Database as UsersDB
from database.queue import QueueDB, WEEKDAY_WINDOWS
from database.notifications import NotificationsDB
from utils.schedule import normalize_schedule_input, parse_schedule_definition

logger = logging.getLogger(__name__)

# Временное хранилище для медиагрупп
_media_groups: dict[str, list[dict]] = {}
# Хранилище caption для медиагрупп (чтобы знать, что медиагруппа с #клининг)
_media_group_captions: dict[str, str] = {}
# Хранилище активных задач обработки медиагрупп
_media_group_tasks: dict[str, asyncio.Task] = {}


# Local databases (same DB file used elsewhere)
udb = UsersDB('fio.db')
qdb = QueueDB('fio.db')
nodb = NotificationsDB('fio.db')

group_router = Router()

# Apply router-wide filter: handle only in groups/supergroups
group_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
group_router.callback_query.filter(F.message.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


DUTY_CHAT_ID = -1003241813302
DUTY_THREAD_ID = 64
DUTY_THREAD_CLEANUP_DAYS = 14
DUTY_CLEANING_THREAD_ID = 5  # Тема "Клининг"
SUPERS_GROUP_ID = -1003283404598
SUPERS_PAYMENT_THREAD_ID = 81  # Тема "Оплата"
COMMON_GROUP_ID = -1003258837348
IMPORTANT_GROUP_ID = -1003267461863
KROME_RABOTY_GROUP_ID = -1003280894419
SUPERS_THREAD_ID = 1
CLEANING_GROUP_ID = -1003308152828


# Отладочный обработчик для логирования всех команд в группах
@group_router.message(F.text.startswith('/'))
async def log_all_commands(message: types.Message):
    """Логирование всех команд для отладки"""
    logger.info(
        f'[DEBUG] Команда в группе: command={message.text}, '
        f'user_id={message.from_user.id}, chat_id={message.chat.id}, '
        f'thread_id={message.message_thread_id}'
    ) 

def _find_window_for_time(day: str, now_time: time) -> str | None:
    windows = WEEKDAY_WINDOWS.get(day, [])
    for w in windows:
        start_s, end_s = w.split('-')
        sh, sm = map(int, start_s.split(':'))
        eh, em = map(int, end_s.split(':'))
        start_t = time(sh, sm)
        end_t = time(eh % 24, em)
        if start_t <= now_time < end_t if start_t < end_t else (now_time >= start_t or now_time < end_t):
            return w
    return None


def _get_usernames_for_slot(day: str, window: str) -> list[str]:
    trainer_ids = qdb.get_trainers_for(day, window)
    id_to_un = {tid: uname for tid, _, uname in udb.list_trainers()}
    usernames: list[str] = []
    for tid in trainer_ids[:2]:
        un = id_to_un.get(tid)
        if un:
            usernames.append(un)
    return usernames


def _get_duty_mentions(day: str, window: str | None) -> list[str]:
    if not window:
        return []
    usernames = _get_usernames_for_slot(day, window)
    return [f"@{uname}" for uname in usernames[:2] if uname]


def _compose_like_suffix(day: str, window: str | None) -> str:
    mentions = _get_duty_mentions(day, window)
    return (' ' + ' '.join(mentions)) if mentions else ''


def _compose_duty_text(day: str, window: str | None) -> str:
    mentions = _get_duty_mentions(day, window)
    if mentions:
        return f"Текущие дежурные: {' '.join(mentions)}"
    return "Текущие дежурные не назначены."


async def notify_dev_birthday(bot: Bot):
    text = (
        'Сегодня у нас особое уведомление, для особого случая!\n'
        'В этот день, 23 августа, свой день рождение отмечает @iFitman!\n'
        'Ваш ученик и по совместительству разработчик от лица @MakeMeetingBot поздравляет лучшего тренера '
        'с днем рождения и желает счастья, здоровья(с такой работой это обязательно), успехов по жизни '
        'и самое главное - хороших клиентов!\n\n'
        'p.s надеюсь, что это уведомление сработает без тестирования😁'
    )
    try:
        await bot.send_message(KROME_RABOTY_GROUP_ID, text)
    except Exception as e:
        print(f'Ошибка отправки спец-уведомления 23 августа: {e}')


async def _handle_audit_phrase(message: types.Message, bot: Bot):
    """Общая логика обработки фразы об аудите."""
    base = (
        'АУДИТ В КЛУБЕ :\n'
        '———————————————\n'
        'Коллеги, кто в клубе - проверьте наличие бейджа и его расположение , собранные волосы, застегнутые кофты (если футба не DDX), не используйте смартфон более минуты \n\n'
        'Будьте, пожалуйста, приветливы 🤗 и поздоровайтесь при встрече с аудитором.\n\n'
        'Дежурный, подойди пожалуйста ближе к ресепшен , узнай нужна ли какая-то помощь.'
    )
    weekdays = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
    now = datetime.now()
    weekday_name = weekdays[now.weekday()]
    current_window = _find_window_for_time(weekday_name, now.time())
    like_suffix = _compose_like_suffix(weekday_name, current_window)
    text_out = f"{base}\n\nПо прочтении смс прошу поставь лайк{like_suffix}"
    try:
        await bot.send_message(message.chat.id, text_out, reply_to_message_id=message.message_id)
    except Exception as e:
        print(f'Ошибка отправки аудита-уведомления: {e}')


@group_router.message(
    F.chat.id == COMMON_GROUP_ID,
    lambda m: isinstance(m.text, str) and m.text.lower().strip() in {
        'в клубе аудит', 'аудит в клубе', 'проверка в клубе', 'в клубе проверка'
    }
)
async def notify_audit_on_phrase(message: types.Message, bot: Bot):
    await _handle_audit_phrase(message, bot)


@group_router.edited_message(
    F.chat.id == COMMON_GROUP_ID,
    lambda m: isinstance(m.text, str) and m.text.lower().strip() in {
        'в клубе аудит', 'аудит в клубе', 'проверка в клубе', 'в клубе проверка'
    }
)
async def notify_audit_on_phrase_edited(message: types.Message, bot: Bot):
    await _handle_audit_phrase(message, bot)


@group_router.message(
    F.chat.id == COMMON_GROUP_ID, 
    lambda m: isinstance(m.text, str) and 'дежурный' in m.text.lower())
async def notify_dezhurni_on_phrase(message: types.Message, bot: Bot):
    weekdays = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
    now = datetime.now()
    weekday_name = weekdays[now.weekday()]
    current_window = _find_window_for_time(weekday_name, now.time())
    text_out = _compose_duty_text(weekday_name, current_window)
    try:
        await message.reply(text_out)
    except Exception as e:
        print(f'Ошибка отправки аудита-уведомления: {e}')


@group_router.message(F.entities)
async def handle_bot_mention(message: types.Message, bot: Bot):
    """Обработчик для ответа на упоминания бота в группах"""
    # Проверяем, упомянут ли бот в сообщении
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    if not message.text:
        return
    
    # Проверяем упоминания через entities
    is_mentioned = False
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset:entity.offset + entity.length]
                if mention_text == f"@{bot_username}":
                    is_mentioned = True
                    break
            elif entity.type == "text_mention":
                if entity.user and entity.user.id == bot_info.id:
                    is_mentioned = True
                    break
    
    if is_mentioned:
        # Отвечаем на сообщение в группе
        try:
            await message.reply(
                "Привет! Я бот-секретарь. "
                "Для работы со мной напишите мне в личные сообщения: @MakeMeetingBot"
            )
        except Exception as e:
            logger.error(f'Ошибка ответа на упоминание бота в группе: {e}')


@group_router.message(
    F.chat.id == DUTY_CHAT_ID,
    F.photo
)
async def forward_cleaning_messages(message: types.Message, bot: Bot):
    """Пересылка фото с #клининг из темы клининг в группу клининг."""
    # Логируем все фото из группы дежурства
    thread_id = getattr(message, 'message_thread_id', None)
    logger.info(
        f'[DUTY PHOTO] message_id={message.message_id}, '
        f'thread_id={thread_id}, '
        f'expected_thread={DUTY_CLEANING_THREAD_ID}, '
        f'caption="{message.caption}", '
        f'media_group_id={message.media_group_id}, '
        f'has_photo={bool(message.photo)}'
    )
    
    # Проверяем, что сообщение из нужной темы
    if thread_id != DUTY_CLEANING_THREAD_ID:
        logger.info(f'[SKIP THREAD] Пропущено: thread_id {thread_id} != {DUTY_CLEANING_THREAD_ID}')
        return
    
    logger.info(
        f'[CLEANING] Получено фото: message_id={message.message_id}, '
        f'thread_id={thread_id}, '
        f'caption="{message.caption}", '
        f'media_group_id={message.media_group_id}'
    )
    
    if CLEANING_GROUP_ID is None:
        logger.warning('[ERROR] CLEANING_GROUP_ID не установлен, пересылка невозможна')
        return
    
    # Проверяем наличие #клининг в описании
    caption = message.caption or ''
    caption_lower = caption.lower()
    has_hashtag = '#клининг' in caption_lower
    logger.info(f'[CAPTION CHECK] caption="{caption}", lower="{caption_lower}", has_hashtag={has_hashtag}')
    
    # Проверяем, является ли это частью медиагруппы
    media_group_id = message.media_group_id
    
    # Если это медиагруппа, проверяем, обрабатывается ли она уже
    if media_group_id:
        group_key = f"{DUTY_CHAT_ID}_{DUTY_CLEANING_THREAD_ID}_{media_group_id}"
        
        # Если медиагруппа уже обрабатывается (значит первое фото с #клининг уже было)
        if group_key in _media_group_captions:
            logger.info(f'[MEDIA GROUP ADD] Добавляем фото к существующей медиагруппе с #клининг: {group_key}')
            # Добавляем фото к существующей медиагруппе, даже если у него нет caption
            photo = message.photo[-1]
            _media_groups[group_key].append({
                'file_id': photo.file_id
            })
            logger.info(f'[MEDIA GROUP ADD] Добавлено фото в медиагруппу {group_key}, всего фото: {len(_media_groups[group_key])}')
            
            # Перезапускаем таймер
            if group_key in _media_group_tasks:
                old_task = _media_group_tasks[group_key]
                if not old_task.done():
                    old_task.cancel()
                    logger.info(f'[MEDIA GROUP] Отменена предыдущая задача для {group_key}')
            
            # Создаем новую задачу с задержкой
            saved_caption = _media_group_captions[group_key]
            task = asyncio.create_task(_process_cleaning_media_group(group_key, bot, saved_caption))
            _media_group_tasks[group_key] = task
            logger.info(f'[MEDIA GROUP] Перезапущена задача обработки медиагруппы: {group_key}')
            return
    
    # Если нет хештега и это не часть уже обрабатываемой медиагруппы - пропускаем
    if not has_hashtag:
        logger.info(f'[SKIP HASHTAG] Пропущено фото без #клининг в описании: caption="{caption}"')
        return
    
    logger.info(f'[FOUND CLEANING] Найдено фото с #клининг: message_id={message.message_id}, caption="{caption}"')
    
    try:
        if media_group_id:
            # Это медиагруппа - сохраняем информацию
            group_key = f"{DUTY_CHAT_ID}_{DUTY_CLEANING_THREAD_ID}_{media_group_id}"
            logger.info(f'[MEDIA GROUP] Обработка медиагруппы: media_group_id={media_group_id}, group_key={group_key}')
            
            # Сохраняем информацию о фото
            photo = message.photo[-1]  # Берем самое большое фото
            
            if group_key not in _media_groups:
                _media_groups[group_key] = []
                _media_group_captions[group_key] = caption  # Сохраняем caption для медиагруппы
                logger.info(f'[MEDIA GROUP] Создана новая медиагруппа: {group_key}, caption="{caption}"')
            
            _media_groups[group_key].append({
                'file_id': photo.file_id
            })
            logger.info(f'[MEDIA GROUP] Добавлено фото в медиагруппу {group_key}, всего фото: {len(_media_groups[group_key])}')
            
            # Запускаем/перезапускаем задачу для обработки медиагруппы
            # Отменяем предыдущую задачу, если она существует
            if group_key in _media_group_tasks:
                old_task = _media_group_tasks[group_key]
                if not old_task.done():
                    old_task.cancel()
                    logger.info(f'[MEDIA GROUP] Отменена предыдущая задача для {group_key}')
            
            # Создаем новую задачу с задержкой
            task = asyncio.create_task(_process_cleaning_media_group(group_key, bot, caption))
            _media_group_tasks[group_key] = task
            logger.info(f'[MEDIA GROUP] Запущена задача обработки медиагруппы: {group_key}, текущее количество фото: {len(_media_groups[group_key])}')
        else:
            # Одиночное фото
            photo = message.photo[-1]
            await bot.send_photo(
                CLEANING_GROUP_ID,
                photo.file_id,
                caption=caption if caption else None
            )
            logger.info(f'Фото с #клининг переслано в группу клининг (message_id={message.message_id})')
    except Exception as e:
        logger.error(f'Ошибка пересылки фото с #клининг: {e}', exc_info=True)


@group_router.message(F.chat.id == DUTY_CHAT_ID)
async def track_duty_thread_messages(message: types.Message):
    """Отслеживание сообщений в теме 'прием смен' (thread_id=64) группы дежурства."""
    thread_id = getattr(message, 'message_thread_id', None)
    if thread_id != DUTY_THREAD_ID:
        return
    if message.message_id is None:
        return
    created_at = datetime.utcnow().isoformat()
    try:
        nodb.add_thread_message(DUTY_CHAT_ID, DUTY_THREAD_ID, message.message_id, created_at)
        logger.debug(f'[TRACK] Сохранено сообщение {message.message_id} из темы дежурств (thread_id={thread_id})')
    except Exception as e:
        logger.error(f'[TRACK] Ошибка сохранения сообщения {message.message_id} из темы дежурств: {e}', exc_info=True)


@group_router.message(F.chat.id == SUPERS_GROUP_ID)
async def track_payment_thread_messages(message: types.Message):
    """Отслеживание сообщений в теме 'Оплата' (thread_id=81) группы Суперы."""
    if getattr(message, 'message_thread_id', None) != SUPERS_PAYMENT_THREAD_ID:
        return
    if message.message_id is None:
        return
    created_at = datetime.utcnow().isoformat()
    try:
        nodb.add_thread_message(SUPERS_GROUP_ID, SUPERS_PAYMENT_THREAD_ID, message.message_id, created_at)
    except Exception as e:
        print(f'Ошибка сохранения сообщения из темы оплаты: {e}')


async def _process_cleaning_media_group(group_key: str, bot: Bot, caption: str):
    """Обрабатывает медиагруппу после небольшой задержки для сбора всех фото."""
    logger.info(f'[MEDIA GROUP PROCESS] Начало обработки медиагруппы: {group_key}')
    await asyncio.sleep(3)  # Ждем 3 секунды, чтобы собрать все сообщения группы
    logger.info(f'[MEDIA GROUP PROCESS] Проснулись после задержки: {group_key}')
    
    if group_key not in _media_groups:
        logger.warning(f'[MEDIA GROUP PROCESS] Медиагруппа {group_key} не найдена в хранилище')
        return
    
    media_items = _media_groups[group_key]
    if not media_items:
        logger.warning(f'[MEDIA GROUP PROCESS] Медиагруппа {group_key} пуста')
        if group_key in _media_groups:
            del _media_groups[group_key]
        return
    
    logger.info(f'[MEDIA GROUP PROCESS] Отправка медиагруппы: {group_key}, фото: {len(media_items)}')
    
    try:
        media_list = []
        for idx, item in enumerate(media_items):
            media_list.append(
                InputMediaPhoto(
                    media=item['file_id'],
                    caption=caption if idx == 0 else None  # Caption только для первого фото
                )
            )
        
        await bot.send_media_group(
            CLEANING_GROUP_ID,
            media=media_list
        )
        logger.info(f'Медиагруппа с #клининг переслана в группу клининг (group_key={group_key}, фото: {len(media_list)})')
    except Exception as e:
        logger.error(f'Ошибка пересылки медиагруппы с #клининг: {e}', exc_info=True)
    finally:
        # Очищаем из хранилища
        if group_key in _media_groups:
            del _media_groups[group_key]
            logger.info(f'[MEDIA GROUP PROCESS] Медиагруппа {group_key} удалена из хранилища')
        if group_key in _media_group_captions:
            del _media_group_captions[group_key]
            logger.info(f'[MEDIA GROUP PROCESS] Caption {group_key} удален из хранилища')
        if group_key in _media_group_tasks:
            del _media_group_tasks[group_key]
            logger.info(f'[MEDIA GROUP PROCESS] Задача {group_key} удалена из хранилища задач')


async def cleanup_duty_thread_messages(bot: Bot):
    """Автоочистка отключена по требованию — выходим без действий."""
    try:
        logger.info('[CLEANUP] Автоочистка отключена, задача пропущена')
    except Exception:
        # Не позволяем задаче упасть даже если логирование даст сбой
        pass


async def cleanup_payment_thread_messages(bot: Bot):
    """Удаление всех сообщений в теме 'Оплата' (thread_id=81) группы Суперы."""
    records = nodb.get_thread_messages_by_chat_and_thread(SUPERS_GROUP_ID, SUPERS_PAYMENT_THREAD_ID)
    deleted_count = 0
    failed_count = 0
    
    for record in records:
        record_id = record['id']
        message_id = record['message_id']
        try:
            await bot.delete_message(SUPERS_GROUP_ID, message_id)
            deleted_count += 1
        except Exception as e:
            print(f'Ошибка удаления сообщения {message_id} из темы оплаты: {e}')
            failed_count += 1
        finally:
            nodb.remove_thread_message(record_id)
    
    print(f'Очистка темы оплаты завершена: удалено {deleted_count}, ошибок {failed_count}')


async def process_scheduled_notifications(bot: Bot):
    notifications = nodb.list_scheduled_notifications()
    if not notifications:
        return

    now = datetime.now()
    current_time = now.strftime('%H:%M')
    today_iso = now.date().isoformat()
    weekdays = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
    weekday_name = weekdays[now.weekday()]

    logger.debug(f'Проверка уведомлений в {current_time}. Всего уведомлений: {len(notifications)}')

    for notif in notifications:
        notif_id = notif.get('id')
        notif_title = notif.get('title', 'без названия')
        
        if not notif.get('enabled', True):
            logger.debug(f'Уведомление {notif_id} "{notif_title}" пропущено: отключено')
            continue
        schedule = parse_schedule_definition(notif.get('time'))
        if not schedule:
            logger.debug(f'Уведомление {notif_id} "{notif_title}" пропущено: не удалось распарсить расписание')
            continue
        if schedule.get('time') != current_time:
            logger.debug(f'Уведомление {notif_id} "{notif_title}": время не совпадает ({schedule.get("time")} != {current_time})')
            continue
        schedule_type = schedule.get('type', 'daily')
        if schedule_type == 'weekly' and schedule.get('weekday') != now.weekday():
            logger.debug(f'Уведомление {notif_id} "{notif_title}": день недели не совпадает (weekly)')
            continue
        if schedule_type == 'monthly_day' and schedule.get('day') != now.day:
            logger.debug(f'Уведомление {notif_id} "{notif_title}": день месяца не совпадает ({schedule.get("day")} != {now.day})')
            continue
        if schedule_type == 'monthly_last':
            last_day = calendar.monthrange(now.year, now.month)[1]
            if now.day != last_day:
                logger.debug(f'Уведомление {notif_id} "{notif_title}": не последний день месяца ({now.day} != {last_day})')
                continue
        if schedule_type == 'annual':
            target = schedule.get('date')
            if not target or (now.month, now.day) != tuple(target):
                logger.debug(f'Уведомление {notif_id} "{notif_title}": дата не совпадает (annual)')
                continue
        if notif.get('last_sent') == today_iso:
            logger.info(f'Уведомление {notif_id} "{notif_title}" пропущено: уже отправлено сегодня ({today_iso})')
            continue
        
        logger.info(f'Найдено уведомление для отправки: {notif_id} "{notif_title}" в {current_time}')

        # Получаем основной текст
        text = notif.get('message', '')
        
        # Если у уведомления есть тексты по дням недели, добавляем текст для текущего дня
        weekday_messages = notif.get('weekday_messages')
        if weekday_messages and isinstance(weekday_messages, dict):
            day_text = weekday_messages.get(weekday_name)
            if day_text:
                text = f"{text}\n\n{day_text}"
        
        mention_suffix = ''
        mention_mode = notif.get('mention_mode', 'none')

        if mention_mode == 'duty_auto':
            try:
                hh, mm = map(int, schedule['time'].split(':'))
                window = _find_window_for_time(weekday_name, time(hh, mm))
            except ValueError:
                window = None
            mention_suffix = _compose_like_suffix(weekday_name, window)
        elif mention_mode == 'manual':
            manual = notif.get('manual_mentions', '').strip()
            if manual:
                mention_suffix = ' ' + manual

        if mention_suffix.strip():
            message_text = f"{text}\n\n{mention_suffix.strip()}" if text else mention_suffix.strip()
        else:
            message_text = text

        groups = notif.get('groups', [])
        if not groups:
            continue

        # Отслеживаем успешность отправки хотя бы в одну группу
        at_least_one_success = False
        
        for entry in groups:
            if isinstance(entry, dict):
                group_id = int(entry.get('group_id'))
                thread_id = entry.get('thread_id')
                thread_id = None if thread_id in (None, '', 0) else int(thread_id)
            else:
                group_id = int(entry)
                thread_id = None
            try:
                await bot.send_message(
                    group_id,
                    message_text,
                    message_thread_id=thread_id if thread_id else None
                )
                at_least_one_success = True
                logger.info(f'Уведомление {notif_id} "{notif_title}" успешно отправлено в группу {group_id}' + (f' (тема {thread_id})' if thread_id else ''))
            except Exception as e:
                logger.error(f'Ошибка отправки уведомления {notif_id} "{notif_title}" в группу {group_id}: {e}')

        # Обновляем статус только если хотя бы одна отправка была успешной
        if at_least_one_success:
            if notif.get('is_one_time', False):
                logger.info(f'Уведомление {notif_id} "{notif_title}" удалено (одноразовое)')
                nodb.delete_scheduled_notification(notif['id'])
            else:
                nodb.update_notification_last_sent(notif['id'], today_iso)
                logger.info(f'Уведомление {notif_id} "{notif_title}": статус обновлен (last_sent={today_iso})')
        else:
            # Если все отправки провалились, логируем это
            logger.warning(f'ВНИМАНИЕ: Уведомление {notif_id} "{notif_title}" не было отправлено ни в одну группу. Статус не обновлен.')

