from buttons.calendar import calendar_month, calendar_day, calendar_time
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ReplyKeyboardMarkup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType
from datetime import *
from aiogram.fsm.state import State, StatesGroup
from buttons.buttons_admin import admin_kb, change_kb, confirm_kb, nachalo_kb, trener_kb, confirm_trainer_kb, queue_days_kb, cancel_kb
from aiogram.fsm.context import FSMContext
from database.meet import Database1
# TrainersDB удален — вся логика перенесена в users
from database.client import Database as UsersDB
from database.queue import QueueDB, WEEKDAY_WINDOWS
from aiogram.types import ReplyKeyboardRemove
from database.notifications import NotificationsDB
from services.google_sheets import GoogleSheetsService
import os
import re
import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from buttons.calendar import months
from utils.schedule import normalize_schedule_input
import html
import asyncio

logger = logging.getLogger(__name__)

db=Database1('fio.db')
udb=UsersDB('fio.db')
qdb=QueueDB('fio.db')
nodb=NotificationsDB('fio.db')
admin_router = Router()
admin_router.message.filter(F.chat.type == ChatType.PRIVATE)
admin_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

# Initialize Google Sheets service if configured
sheets_id = os.getenv('GOOGLE_SHEETS_ID')
sheets_service = GoogleSheetsService(sheets_id) if sheets_id else None

SUPERS_GROUP_ID = -1003283404598
WORK_BDAY_GROUP_ID = -1003280894419
COMMON_GROUP_ID = -1003258837348
DUTY_GROUP_ID = -1003241813302
IMPORTANT_GROUP_ID = -1003267461863

THREADED_GROUPS = {SUPERS_GROUP_ID, DUTY_GROUP_ID}
THREADED_DEFAULT_THREADS = {
    SUPERS_GROUP_ID: 1,
    DUTY_GROUP_ID: 64,
}

# Notification groups available for scheduling
NOTIFICATION_GROUPS = [
    ('Суперы', SUPERS_GROUP_ID),
    ('Общая группа', COMMON_GROUP_ID),
    ('Дежурства', DUTY_GROUP_ID),
    ('Кроме работы', WORK_BDAY_GROUP_ID),
    ('Важное', IMPORTANT_GROUP_ID),
]
GROUP_INDEX_MAP = {str(index + 1): gid for index, (_, gid) in enumerate(NOTIFICATION_GROUPS)}
GROUP_ID_TO_NAME = {gid: name for name, gid in NOTIFICATION_GROUPS}

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

TRAINER_FIELDS = [
    ('ФИО', 'nickname'),
    ('Телефон', 'phone'),
    ('Дата рождения', 'birthday'),
    ('Статус занятости', 'employment_type'),
    ('Email', 'email'),
    ('Медкомиссия', 'med_date'),
    ('Повышение квалификации', 'qual_date'),
]

class AddMeet(StatesGroup):
    # Шаги состояний
    day = State()
    name = State()
    time = State()
    month = State()

class ChangeMeet(StatesGroup):
    # Шаги состояний
    month = State()
    day = State()
    time = State()
    vvod = State()
 


class QueueAssign(StatesGroup):
    day = State()
    window = State()
    trainer = State()
    confirm = State()


class TrainerDataStates(StatesGroup):
    select_trainer = State()
    choose_field = State()
    input_value = State()


class NotificationStates(StatesGroup):
    menu = State()
    create_title = State()
    create_description = State()
    create_text = State()
    create_type = State()
    create_time = State()
    create_one_time_month = State()
    create_one_time_day = State()
    create_one_time_time = State()
    create_groups = State()
    create_mention_mode = State()
    create_manual_mentions = State()
    create_group_thread = State()
    create_broadcast_text = State()
    edit_choice = State()
    edit_title = State()
    edit_description = State()
    edit_text = State()
    edit_time = State()
    edit_groups = State()
    edit_mention_mode = State()
    edit_manual_mentions = State()
    edit_group_thread = State()
    delete_confirm = State()
    # Состояния для уведомлений с текстами по дням недели
    create_weekday_base_text = State()
    create_weekday_monday = State()
    create_weekday_tuesday = State()
    create_weekday_wednesday = State()
    create_weekday_thursday = State()
    create_weekday_friday = State()
    create_weekday_saturday = State()
    create_weekday_sunday = State()


def _notification_groups_text() -> str:
    lines = []
    for index, (name, gid) in enumerate(NOTIFICATION_GROUPS, start=1):
        lines.append(f"{index}. {name} ({gid})")
    return '\n'.join(lines)


def _resolve_group_names(group_entries) -> list[str]:
    names: list[str] = []
    for entry in group_entries:
        if isinstance(entry, dict):
            group_id = int(entry.get('group_id'))
            thread_id = entry.get('thread_id')
        else:
            group_id = int(entry)
            thread_id = None
        name = GROUP_ID_TO_NAME.get(group_id, str(group_id))
        if thread_id:
            name = f"{name} (тема {thread_id})"
        names.append(name)
    return names


def _format_schedule_display(schedule_str: str) -> str:
    """Форматирует расписание для отображения с русскими днями недели."""
    if not schedule_str:
        return schedule_str
    weekday_map = {
        'mon': 'Понедельник',
        'tue': 'Вторник',
        'wed': 'Среда',
        'thu': 'Четверг',
        'fri': 'Пятница',
        'sat': 'Суббота',
        'sun': 'Воскресенье',
    }
    parts = schedule_str.split()
    if len(parts) == 2:
        day_tokens = parts[0].split(',')
        if all(t in weekday_map for t in day_tokens):
            day_names = ', '.join(weekday_map[t] for t in day_tokens)
            return f"{day_names} {parts[1]}"
        elif parts[0] in weekday_map:
            return f"{weekday_map[parts[0]]} {parts[1]}"
        elif parts[0].startswith('day='):
            day_num = parts[0].replace('day=', '')
            return f"День {day_num} {parts[1]}"
        elif parts[0] == 'last':
            return f"Последний день месяца {parts[1]}"
        elif parts[0].startswith('date='):
            date_part = parts[0].replace('date=', '')
            month, day = date_part.split('-')
            months_ru = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
            try:
                month_name = months_ru[int(month) - 1]
                return f"{int(day)} {month_name} {parts[1]}"
            except (ValueError, IndexError):
                return schedule_str
    return schedule_str


def _mention_mode_description(mode: str, manual: str = '') -> str:
    if mode == 'duty_auto':
        return 'Тегать дежурных по расписанию'
    if mode == 'manual':
        return f'Указать вручную ({manual})' if manual else 'Указать вручную'
    return 'Без упоминания'


def _normalize_time_string(value: str) -> str | None:
    return normalize_schedule_input(value)


def _parse_group_selection(text: str) -> list[int] | None:
    text = text.replace(',', ' ').strip()
    if not text:
        return None
    tokens = [token.strip() for token in text.split() if token.strip()]
    selected: set[int] = set()
    for token in tokens:
        lower = token.lower()
        if lower in {'все', 'all'}:
            return [gid for _, gid in NOTIFICATION_GROUPS]
        if token in GROUP_INDEX_MAP:
            selected.add(GROUP_INDEX_MAP[token])
            continue
        try:
            gid = int(token)
            if gid in GROUP_ID_TO_NAME:
                selected.add(gid)
                continue
        except ValueError:
            pass
        return None
    return sorted(selected)


WEEKDAY_OPTIONS = [
    ('Пн', 'mon', 0),
    ('Вт', 'tue', 1),
    ('Ср', 'wed', 2),
    ('Чт', 'thu', 3),
    ('Пт', 'fri', 4),
    ('Сб', 'sat', 5),
    ('Вс', 'sun', 6),
]


def _notifications_menu_markup(notifications: list[dict], page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    notifications = sorted(notifications, key=lambda n: n['id'])
    total = len(notifications)
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total)
    page_notifications = notifications[start_idx:end_idx]
    
    for notif in page_notifications:
        builder.button(
            text=f"{notif['id']}. {notif['title'][:40]}",
            callback_data=f'notif|edit|{notif["id"]}'
        )
    
    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text='⬅️ Назад', callback_data=f'notif|page|{page-1}'))
    if end_idx < total:
        nav_buttons.append(InlineKeyboardButton(text='Вперёд ➡️', callback_data=f'notif|page|{page+1}'))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.button(text='➕ Создать уведомление', callback_data='notif|create')
    builder.button(text='⬅️ Назад', callback_data='notif|back')
    return builder.adjust(1).as_markup()


def _notification_edit_markup(notif_id: int, enabled: bool = True, is_one_time: bool = False, has_weekday_messages: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Название', callback_data=f'notif|field|title|{notif_id}')
    builder.button(text='Описание', callback_data=f'notif|field|description|{notif_id}')
    builder.button(text='Текст', callback_data=f'notif|field|text|{notif_id}')
    builder.button(text='Расписание', callback_data=f'notif|field|schedule|{notif_id}')
    builder.button(text='Группы', callback_data=f'notif|field|groups|{notif_id}')
    builder.button(text='Упоминания', callback_data=f'notif|field|mentions|{notif_id}')
    if has_weekday_messages:
        builder.button(text='👁️ Предпросмотр', callback_data=f'notif|preview|{notif_id}')
    enabled_text = '❌ Выключить' if enabled else '✅ Включить'
    builder.button(text=enabled_text, callback_data=f'notif|toggle|{notif_id}')
    type_text = 'Повторяющееся' if is_one_time else 'Одноразовое'
    button_text = 'Одноразки' if is_one_time else 'Повторяющееся'
    builder.button(text=button_text, callback_data=f'notif|toggletime|{notif_id}')
    builder.button(text='Удалить', callback_data=f'notif|delete|{notif_id}')
    builder.button(text='⬅️ В меню', callback_data='notif|menu')
    return builder.adjust(2).as_markup()


def _schedule_type_markup(mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Каждый день', callback_data=f'notif|schedtype|{mode}|daily')
    builder.button(text='По дням недели', callback_data=f'notif|schedtype|{mode}|weekly')
    builder.button(text='По дате месяца', callback_data=f'notif|schedtype|{mode}|monthday')
    builder.button(text='В последний день месяца', callback_data=f'notif|schedtype|{mode}|lastday')
    builder.button(text='Раз в год', callback_data=f'notif|schedtype|{mode}|annual')
    builder.button(text='⬅️ Отмена', callback_data=f'notif|schedcancel|{mode}')
    return builder.adjust(1).as_markup()


def _weekday_selection_text(selected: set[str]) -> str:
    if not selected:
        return 'Выберите дни недели для отправки уведомления.'
    names = [label for label, code, _ in WEEKDAY_OPTIONS if code in selected]
    return f'Выбранные дни: {", ".join(names)}\n\nНажмите «Готово» для подтверждения.'


def _weekday_selection_markup(selected: set[str], mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, code, _ in WEEKDAY_OPTIONS:
        mark = '✅' if code in selected else '▫️'
        builder.button(text=f'{mark} {label}', callback_data=f'notif|schedweekday|{mode}|{code}')
    builder.button(text='Готово', callback_data=f'notif|weekdaydone|{mode}')
    builder.button(text='⬅️ Назад', callback_data=f'notif|schedcancel|{mode}')
    return builder.adjust(3).as_markup()


def _day_of_month_markup(mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in range(1, 32):
        builder.button(text=str(day), callback_data=f'notif|schedday|{mode}|{day}')
    builder.button(text='⬅️ Назад', callback_data=f'notif|schedcancel|{mode}')
    return builder.adjust(7).as_markup()


def _annual_month_markup(mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for idx, mo in enumerate(months, start=1):
        builder.button(text=mo.capitalize(), callback_data=f'notif|schedmonth|{mode}|{idx}')
    builder.button(text='⬅️ Назад', callback_data=f'notif|schedcancel|{mode}')
    return builder.adjust(3).as_markup()


def _annual_day_markup(mode: str, month_index: int) -> InlineKeyboardMarkup:
    if month_index == 2:
        days_in_month = 29
    elif month_index in (4, 6, 9, 11):
        days_in_month = 30
    else:
        days_in_month = 31
    builder = InlineKeyboardBuilder()
    for day in range(1, days_in_month + 1):
        builder.button(text=str(day), callback_data=f'notif|schedannualday|{mode}|{day}')
    builder.button(text='⬅️ Назад', callback_data=f'notif|schedmonthback|{mode}')
    return builder.adjust(7).as_markup()


def _time_selection_markup(mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for hour in range(0, 24):
        for minute in (0, 30):
            value = f"{hour:02d}:{minute:02d}"
            builder.button(text=value, callback_data=f'notif|schedtime|{mode}|{value}')
    builder.button(text='⬅️ Назад', callback_data=f'notif|schedcancel|{mode}')
    return builder.adjust(4).as_markup()


def _group_selection_text(selected: set[int]) -> str:
    if not selected:
        return 'Выберите группы, куда будет отправляться уведомление.'
    lines = ['Текущий выбор:']
    for name, gid in NOTIFICATION_GROUPS:
        if gid in selected:
            lines.append(f'• {name} ({gid})')
    return '\n'.join(lines)


def _group_selection_markup(selected: set[int], mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, gid in NOTIFICATION_GROUPS:
        mark = '✅' if gid in selected else '▫️'
        builder.button(text=f'{mark} {name}', callback_data=f'notif|group|{mode}|{gid}')
    builder.button(text='Готово', callback_data=f'notif|groupdone|{mode}')
    builder.button(text='⬅️ Отмена', callback_data=f'notif|groupcancel|{mode}')
    return builder.adjust(1).as_markup()


def _mention_mode_markup(mode: str, current: str | None = None) -> InlineKeyboardMarkup:
    options = [
        ('Без тегов', 'none'),
        ('Дежурные по расписанию', 'duty_auto'),
        ('Указать вручную', 'manual'),
    ]
    builder = InlineKeyboardBuilder()
    for label, value in options:
        mark = '✅ ' if current == value else ''
        builder.button(text=f'{mark}{label}', callback_data=f'notif|mention|{mode}|{value}')
    builder.button(text='⬅️ Отмена', callback_data=f'notif|mentioncancel|{mode}')
    return builder.adjust(1).as_markup()


async def _start_schedule_selection(target: types.Message | CallbackQuery, state: FSMContext, mode: str):
    flow = {'mode': mode}
    if mode == 'edit':
        flow['notif_id'] = (await state.get_data()).get('edit_notification_id')
    await state.update_data(schedule_flow=flow)
    text = 'Выберите тип расписания:'
    markup = _schedule_type_markup(mode)
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


async def _start_group_selection(
    target: types.Message | CallbackQuery,
    state: FSMContext,
    mode: str,
    existing_notif: dict | None = None
):
    state_data = await state.get_data()
    if mode == 'edit' and not existing_notif:
        notif_id = state_data.get('edit_notification_id')
        existing_notif = nodb.get_scheduled_notification(notif_id) if notif_id else None
    selected_set = set()
    if existing_notif:
        selected_set = {entry['group_id'] for entry in existing_notif.get('groups', [])}
    selected_list = sorted(selected_set)
    selection = {'mode': mode, 'selected': selected_list}
    if mode == 'edit':
        selection['notif_id'] = existing_notif['id'] if existing_notif else state_data.get('edit_notification_id')
    await state.update_data(group_selection=selection)
    text = _group_selection_text(set(selected_list))
    markup = _group_selection_markup(set(selected_list), mode)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


async def _start_mention_selection(
    target: types.Message | CallbackQuery,
    state: FSMContext,
    mode: str,
    current_mode: str = 'none'
):
    markup = _mention_mode_markup(mode, current_mode)
    text = 'Выберите режим упоминаний:'
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


async def _complete_schedule_flow(target: types.Message | CallbackQuery, state: FSMContext, normalized: str):
    data = await state.get_data()
    flow = data.get('schedule_flow') or {}
    mode = flow.get('mode')
    await state.update_data(schedule_flow=None)
    if mode == 'edit':
        notif_id = flow.get('notif_id') or data.get('edit_notification_id')
        if notif_id:
            nodb.update_scheduled_notification(notif_id, time=normalized)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text('Расписание обновлено.')
            await _return_to_edit_menu(target, state)
        else:
            await target.answer('Расписание обновлено.')
            await _return_to_edit_menu(target, state)
    else:
        new_notif = data.get('new_notification', {})
        new_notif['time'] = normalized
        await state.update_data(new_notification=new_notif)
        await _start_group_selection(target, state, mode='create')


def _format_notifications_overview(notifications: list[dict], page: int = 0, per_page: int = 10) -> str:
    if not notifications:
        return "Уведомлений пока нет."
    notifications = sorted(notifications, key=lambda n: n['id'])
    total = len(notifications)
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total)
    page_notifications = notifications[start_idx:end_idx]
    
    lines: list[str] = []
    # Заголовок с информацией о странице
    if total > per_page:
        lines.append(f"📄 Страница {page + 1} из {(total + per_page - 1) // per_page} (показано {start_idx + 1}-{end_idx} из {total})\n")
    
    for notif in page_notifications:
        groups_display = ', '.join(_resolve_group_names(notif['groups'])) or '—'
        mention_desc = _mention_mode_description(
            notif.get('mention_mode', 'none'),
            notif.get('manual_mentions', '')
        )
        description = notif.get('description', '').strip() or 'Без описания'
        enabled = notif.get('enabled', True)
        is_one_time = notif.get('is_one_time', False)
        status = '✅ Вкл' if enabled else '❌ Выкл'
        type_label = 'Одноразовое' if is_one_time else 'Повторяющееся'
        schedule_display = _format_schedule_display(notif['time'])
        lines.append(
            f"{notif['id']}. {notif['title']}\n"
            f"   Описание: {description}\n"
            f"   Статус: {status}\n"
            f"   Тип: {type_label}\n"
            f"   Расписание: {schedule_display}\n"
            f"   Группы: {groups_display}\n"
            f"   Упоминания: {mention_desc}"
        )
    
    text = '\n'.join(lines)
    
    # Если текст слишком длинный, сокращаем информацию
    MAX_LENGTH = 4000  # Оставляем запас для notice и других элементов
    if len(text) > MAX_LENGTH:
        lines_short: list[str] = []
        if total > per_page:
            lines_short.append(f"📄 Страница {page + 1} из {(total + per_page - 1) // per_page} (показано {start_idx + 1}-{end_idx} из {total})\n")
        
        for notif in page_notifications:
            groups_display = ', '.join(_resolve_group_names(notif['groups'])) or '—'
            enabled = notif.get('enabled', True)
            is_one_time = notif.get('is_one_time', False)
            status = '✅ Вкл' if enabled else '❌ Выкл'
            type_label = 'Одноразовое' if is_one_time else 'Повторяющееся'
            schedule_display = _format_schedule_display(notif['time'])
            # Сокращенная версия без описания и упоминаний
            lines_short.append(
                f"{notif['id']}. {notif['title']}\n"
                f"   Статус: {status} | Тип: {type_label} | Расписание: {schedule_display}\n"
                f"   Группы: {groups_display}"
            )
        text = '\n'.join(lines_short)

        # Если все еще слишком длинный, еще больше сокращаем
        if len(text) > MAX_LENGTH:
            lines_minimal: list[str] = []
            if total > per_page:
                lines_minimal.append(f"📄 Страница {page + 1} из {(total + per_page - 1) // per_page} (показано {start_idx + 1}-{end_idx} из {total})\n")
            
            for notif in page_notifications:
                enabled = notif.get('enabled', True)
                status = '✅' if enabled else '❌'
                lines_minimal.append(f"{notif['id']}. {notif['title']} {status}")
            text = '\n'.join(lines_minimal)
    
    return text


async def _send_notifications_menu(target: types.Message | CallbackQuery, state: FSMContext, notice: str | None = None, page: int = 0):
    notifications = nodb.list_scheduled_notifications()
    overview = _format_notifications_overview(notifications, page=page)
    
    # Проверяем лимит Telegram (4096 символов)
    MAX_TELEGRAM_LENGTH = 4096
    
    # Если есть notice, проверяем его длину
    if notice and len(notice) > MAX_TELEGRAM_LENGTH:
        # Если notice слишком длинный, обрезаем его
        notice = notice[:MAX_TELEGRAM_LENGTH - 50] + "\n\n... (уведомление обрезано)"
    
    # Формируем финальный текст с учетом notice
    if notice:
        # Пробуем объединить notice и overview
        text = f"{notice}\n\n{overview}"
        # Если объединенный текст слишком длинный, отправляем notice отдельно
        if len(text) > MAX_TELEGRAM_LENGTH:
            if isinstance(target, CallbackQuery):
                await target.message.answer(notice)
            else:
                await target.answer(notice)
            text = overview
    else:
        text = overview
    
    # Если текст все еще слишком длинный, обрезаем его
    if len(text) > MAX_TELEGRAM_LENGTH:
        text = text[:MAX_TELEGRAM_LENGTH - 50] + "\n\n... (текст обрезан из-за ограничения Telegram)"
    
    markup = _notifications_menu_markup(notifications, page=page)
    await state.update_data(notifications_page=page)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)
    await state.set_state(NotificationStates.menu)


async def _show_notification_edit_menu(target: types.Message | CallbackQuery, notif: dict):
    groups_display = ', '.join(_resolve_group_names(notif['groups'])) or '—'
    mention_desc = _mention_mode_description(
        notif.get('mention_mode', 'none'),
        notif.get('manual_mentions', '')
    )
    enabled = notif.get('enabled', True)
    is_one_time = notif.get('is_one_time', False)
    status = '✅ Включено' if enabled else '❌ Выключено'
    type_label = 'Одноразовое' if is_one_time else 'Повторяющееся'
    schedule_display = _format_schedule_display(notif['time'])
    
    # Формируем текст сообщения с упоминаниями после него
    message_text = notif['message']
    mention_mode = notif.get('mention_mode', 'none')
    if mention_mode == 'manual':
        manual_mentions = notif.get('manual_mentions', '').strip()
        if manual_mentions:
            message_text = f"{message_text}\n\n{manual_mentions}"
    elif mention_mode == 'duty_auto':
        # Для режима дежурных показываем, что будут тегаться дежурные
        message_text = f"{message_text}\n\n[Будут упомянуты дежурные по расписанию]"
    
    text = (
        f"Уведомление #{notif['id']} — {notif['title']}\n"
        f"Описание: {notif.get('description') or '—'}\n"
        f"Статус: {status}\n"
        f"Тип: {type_label}\n"
        f"Расписание: {schedule_display}\n"
        f"Группы: {groups_display}\n"
        f"Упоминания: {mention_desc}\n"
        f"Текст:\n{message_text}"
    )
    # Проверяем, есть ли тексты по дням недели
    has_weekday_messages = bool(notif.get('weekday_messages'))
    markup = _notification_edit_markup(notif['id'], enabled, is_one_time, has_weekday_messages)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


def _clone_group_entries(raw_entries) -> list[dict]:
    cloned: list[dict] = []
    for entry in raw_entries:
        if isinstance(entry, dict):
            cloned.append({
                'group_id': int(entry.get('group_id')),
                'thread_id': entry.get('thread_id') if entry.get('thread_id') not in (None, '', 0) else None,
            })
        else:
            cloned.append({'group_id': int(entry), 'thread_id': None})
    return cloned


async def _ask_next_thread(message: types.Message, state: FSMContext, create_flow: bool):
    """
    Запрашивает ввод thread_id для групп с темами.
    Всегда запрашивает ручной ввод ID темы.
    """
    data = await state.get_data()
    prompts = data.get('thread_prompt_list', [])
    index = data.get('thread_prompt_index', 0)
    while index < len(prompts):
        entry = prompts[index]
        group_id = entry.get('group_id')
        # Для Суперы и Дежурства всегда запрашиваем thread_id
        needs_prompt = False
        if _needs_thread(group_id):
            # Всегда запрашиваем для Суперы и Дежурства
            needs_prompt = True
        if needs_prompt:
            group_name = GROUP_ID_TO_NAME.get(group_id, str(group_id))
            await state.update_data(thread_prompt_index=index)
            
            # Всегда запрашиваем ручной ввод thread_id
            text = (
            f"Для группы {group_name} введите числовой ID темы.\n\n"
            f"Введите '0' для общего чата (без темы):"
            )
            await message.answer(text)
            await state.set_state(
                NotificationStates.create_group_thread if create_flow else NotificationStates.edit_group_thread
            )
            return
        index += 1
    # no more prompts needed
    if create_flow:
        new_notif = data.get('new_notification', {})
        new_notif['groups'] = prompts
        await state.update_data(new_notification=new_notif, thread_prompt_list=None, thread_prompt_index=0)
        await message.answer('Группы сохранены. Теперь выберите режим упоминаний.')
        await _start_mention_selection(message, state, mode='create', current_mode=new_notif.get('mention_mode', 'none'))
    else:
        notif_id = data.get('edit_notification_id')
        nodb.update_scheduled_notification(notif_id, groups=prompts)
        await message.answer('Группы и темы обновлены.')
        await state.update_data(thread_prompt_list=None, thread_prompt_index=0)
        await _return_to_edit_menu(message, state)


admins=[916539100, 676770835]

@admin_router.message(Command('admin'), F.chat.type == ChatType.PRIVATE)
@admin_router.message(F.text=='Главное меню', F.chat.type == ChatType.PRIVATE)
async def start(message: types.Message, state: FSMContext):
    if message.from_user.id in admins:
        await state.clear()
        await message.answer('Дарова, босс!', reply_markup=nachalo_kb)



@admin_router.message(F.text=='Работа со встречами')
async def rabota_sovstrechami(message: types.Message):
        await message.answer('Вы в меню работы со встречами', reply_markup=admin_kb)


@admin_router.message(F.text=='Работа с тренерами')
async def rabota_sovstrechami(message: types.Message):
        await message.answer('Вы в меню работы с тренерами', reply_markup=trener_kb)


@admin_router.message(F.text=='Работа с уведомлениями')
async def notifications_menu_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in admins:
        return
    await _send_notifications_menu(message, state)


@admin_router.message(NotificationStates.menu)
async def notifications_menu_input(message: types.Message, state: FSMContext):
    await message.answer('Используйте кнопки под сообщением для управления уведомлениями.')


@admin_router.callback_query(F.data.startswith('notif|broadcast|'))
async def notifications_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        notif_id = int(callback.data.split('|')[2])
    except (ValueError, IndexError):
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    await state.update_data(broadcast_notif_id=notif_id)
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Да, отправить', callback_data=f'notif|broadcast_confirm|{notif_id}')
    builder.button(text='❌ Отмена', callback_data='notif|menu')
    await callback.message.edit_text(
        f'Подтвердите отправку рассылки:\n\n'
        f'Текст: {notif["message"][:200]}{"..." if len(notif["message"]) > 200 else ""}\n\n'
        f'Сообщение будет отправлено всем зарегистрированным пользователям в личные сообщения.\n'
        f'Отправка будет происходить с задержкой, чтобы не перегружать сервер.',
        reply_markup=builder.adjust(1).as_markup()
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|broadcast_confirm|'))
async def notifications_broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        notif_id = int(callback.data.split('|')[2])
    except (ValueError, IndexError):
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    user_ids = udb.list_all_users()
    if not user_ids:
        await callback.message.edit_text('Нет пользователей для рассылки.')
        await callback.answer()
        return
    await callback.message.edit_text(f'Начинаю рассылку {len(user_ids)} пользователям...')
    await callback.answer()
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, notif['message'])
            sent += 1
            # Задержка 0.1 секунды между сообщениями, чтобы не перегружать сервер
            await asyncio.sleep(0.1)
        except Exception as e:
            failed += 1
            print(f'Ошибка отправки пользователю {user_id}: {e}')
    await callback.message.answer(
        f'Рассылка завершена!\n'
        f'Отправлено: {sent}\n'
        f'Ошибок: {failed}',
        reply_markup=InlineKeyboardBuilder().button(text='⬅️ В меню', callback_data='notif|menu').adjust(1).as_markup()
    )
    await state.update_data(broadcast_notif_id=None)


@admin_router.callback_query(F.data == 'notif|menu')
async def notifications_menu_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    data = await state.get_data()
    page = data.get('notifications_page', 0)
    await _send_notifications_menu(callback, state, page=page)


@admin_router.callback_query(F.data.startswith('notif|page|'))
async def notifications_page_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        page = int(callback.data.split('|')[2])
    except (ValueError, IndexError):
        await callback.answer('Некорректная страница', show_alert=True)
        return
    await _send_notifications_menu(callback, state, page=page)
    await callback.answer()


@admin_router.callback_query(F.data == 'notif|back')
async def notifications_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer('Возвращаю вас в главное меню.', reply_markup=nachalo_kb)
    await callback.answer()


@admin_router.callback_query(F.data == 'notif|create')
async def notifications_create_start_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    await state.update_data(new_notification={'mention_mode': 'none'})
    # Сначала выбираем тип уведомления
    builder = InlineKeyboardBuilder()
    builder.button(text='Повторяющееся', callback_data='notif|type|create|0')
    builder.button(text='Одноразовое', callback_data='notif|type|create|1')
    builder.button(text='С текстами по дням недели', callback_data='notif|type|create|weekday')
    builder.button(text='Рассылка', callback_data='notif|type|create|broadcast')
    builder.button(text='⬅️ Отмена', callback_data='notif|createcancel')
    await callback.message.answer('Выберите тип уведомления:', reply_markup=builder.adjust(1).as_markup())
    await state.set_state(NotificationStates.create_type)
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|edit|'))
async def notifications_edit_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        notif_id = int(callback.data.split('|')[2])
    except (IndexError, ValueError):
        await callback.answer('Некорректный выбор', show_alert=True)
        return
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    await state.update_data(edit_notification_id=notif_id)
    await _show_notification_edit_menu(callback, notif)
    await state.set_state(NotificationStates.edit_choice)


@admin_router.callback_query(F.data.startswith('notif|schedcancel|'))
async def notifications_schedule_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode = callback.data.split('|')
    if mode == 'edit':
        await state.update_data(schedule_flow=None)
        await callback.message.edit_text('Изменение расписания отменено.')
        await _return_to_edit_menu(callback.message, state)
        await callback.answer()
    else:
        await state.update_data(schedule_flow=None)
        await callback.message.edit_text('Выберите тип расписания:', reply_markup=_schedule_type_markup('create'))
        await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedtype|'))
async def notifications_schedule_type(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        _, _, mode, sched_type = callback.data.split('|', 3)
    except ValueError:
        await callback.answer('Некорректный выбор', show_alert=True)
        return
    data = await state.get_data()
    flow = data.get('schedule_flow') or {}
    flow.update({'mode': mode, 'type': sched_type})
    if mode == 'edit':
        flow['notif_id'] = data.get('edit_notification_id')
    await state.update_data(schedule_flow=flow)
    if sched_type == 'daily':
        await callback.message.edit_text('Выберите время отправки:', reply_markup=_time_selection_markup(mode))
    elif sched_type == 'weekly':
        await callback.message.edit_text(_weekday_selection_text(set()), reply_markup=_weekday_selection_markup(set(), mode))
    elif sched_type == 'monthday':
        await callback.message.edit_text('Выберите число месяца:', reply_markup=_day_of_month_markup(mode))
    elif sched_type == 'lastday':
        await callback.message.edit_text('Выберите время отправки:', reply_markup=_time_selection_markup(mode))
    elif sched_type == 'annual':
        await callback.message.edit_text('Выберите месяц:', reply_markup=_annual_month_markup(mode))
    else:
        await callback.message.edit_text('Неизвестный тип расписания. Попробуйте снова.', reply_markup=_schedule_type_markup(mode))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedweekday|'))
async def notifications_schedule_weekday(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, weekday = callback.data.split('|', 3)
    data = await state.get_data()
    flow = data.get('schedule_flow')
    if not flow:
        await callback.answer('Сначала выберите тип расписания.', show_alert=True)
        return
    selected = set(flow.get('weekdays', []))
    if weekday in selected:
        selected.discard(weekday)
    else:
        selected.add(weekday)
    day_order = {code: i for _, code, i in WEEKDAY_OPTIONS}
    flow['weekdays'] = sorted(selected, key=lambda c: day_order.get(c, 99))
    await state.update_data(schedule_flow=flow)
    await callback.message.edit_text(_weekday_selection_text(selected), reply_markup=_weekday_selection_markup(selected, mode))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|weekdaydone|'))
async def notifications_weekday_done(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode = callback.data.split('|', 2)
    data = await state.get_data()
    flow = data.get('schedule_flow')
    if not flow:
        await callback.answer('Сначала выберите тип расписания.', show_alert=True)
        return
    weekdays = flow.get('weekdays', [])
    if not weekdays:
        await callback.answer('Выберите хотя бы один день.', show_alert=True)
        return
    flow['weekday'] = weekdays[0]
    await state.update_data(schedule_flow=flow)
    await callback.message.edit_text('Выберите время отправки:', reply_markup=_time_selection_markup(mode))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedday|'))
async def notifications_schedule_monthday(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, day_str = callback.data.split('|', 3)
    try:
        day = int(day_str)
    except ValueError:
        await callback.answer('Некорректное число', show_alert=True)
        return
    data = await state.get_data()
    flow = data.get('schedule_flow')
    if not flow:
        await callback.answer('Сначала выберите тип расписания.', show_alert=True)
        return
    flow['day'] = day
    await state.update_data(schedule_flow=flow)
    await callback.message.edit_text('Выберите время отправки:', reply_markup=_time_selection_markup(mode))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedmonth|'))
async def notifications_schedule_month(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, month_str = callback.data.split('|', 3)
    try:
        month = int(month_str)
    except ValueError:
        await callback.answer('Некорректный месяц', show_alert=True)
        return
    data = await state.get_data()
    flow = data.get('schedule_flow')
    if not flow:
        await callback.answer('Сначала выберите тип расписания.', show_alert=True)
        return
    flow['month'] = month
    await state.update_data(schedule_flow=flow)
    await callback.message.edit_text('Выберите день месяца:', reply_markup=_annual_day_markup(mode, month))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedmonthback|'))
async def notifications_schedule_month_back(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode = callback.data.split('|', 2)
    data = await state.get_data()
    flow = data.get('schedule_flow') or {}
    flow.pop('month', None)
    flow.pop('day', None)
    await state.update_data(schedule_flow=flow)
    await callback.message.edit_text('Выберите месяц:', reply_markup=_annual_month_markup(mode))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedannualday|'))
async def notifications_schedule_annual_day(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, day_str = callback.data.split('|', 3)
    try:
        day = int(day_str)
    except ValueError:
        await callback.answer('Некорректная дата', show_alert=True)
        return
    data = await state.get_data()
    flow = data.get('schedule_flow')
    if not flow or not flow.get('month'):
        await callback.answer('Сначала выберите месяц.', show_alert=True)
        return
    flow['day'] = day
    await state.update_data(schedule_flow=flow)
    await callback.message.edit_text('Выберите время отправки:', reply_markup=_time_selection_markup(mode))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|schedtime|'))
async def notifications_schedule_time(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, time_value = callback.data.split('|', 3)
    data = await state.get_data()
    flow = data.get('schedule_flow')
    if not flow:
        await callback.answer('Нет активного выбора расписания.', show_alert=True)
        return
    sched_type = flow.get('type')
    expression = None
    if sched_type == 'daily':
        expression = time_value
    elif sched_type == 'weekly':
        weekdays_list = flow.get('weekdays') or [flow.get('weekday', 'mon')]
        expression = f"{','.join(weekdays_list)} {time_value}"
    elif sched_type == 'monthday':
        day = flow.get('day', 1)
        expression = f"day={day} {time_value}"
    elif sched_type == 'lastday':
        expression = f"last {time_value}"
    elif sched_type == 'annual':
        month = flow.get('month', 1)
        day = flow.get('day', 1)
        expression = f"date={month:02d}-{day:02d} {time_value}"
    else:
        await callback.answer('Неизвестный тип расписания.', show_alert=True)
        return
    normalized = _normalize_time_string(expression)
    if not normalized:
        await callback.answer('Не удалось разобрать время.', show_alert=True)
        return
    await _complete_schedule_flow(callback, state, normalized)


@admin_router.callback_query(F.data.startswith('notif|field|'))
async def notifications_edit_field_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        _, _, field, notif_id_str = callback.data.split('|', 3)
        notif_id = int(notif_id_str)
    except (ValueError, IndexError):
        await callback.answer('Некорректный выбор', show_alert=True)
        return
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    await state.update_data(edit_notification_id=notif_id)
    if field == 'title':
        await callback.message.answer('Введите новое название уведомления:')
        await state.set_state(NotificationStates.edit_title)
        await callback.answer()
        return
    if field == 'description':
        await callback.message.answer('Введите новое описание уведомления:')
        await state.set_state(NotificationStates.edit_description)
        await callback.answer()
        return
    if field == 'text':
        await callback.message.answer('Введите новый текст уведомления:')
        await state.set_state(NotificationStates.edit_text)
        await callback.answer()
        return
    if field == 'schedule':
        await _start_schedule_selection(callback, state, mode='edit')
        return
    if field == 'groups':
        await _start_group_selection(callback, state, mode='edit', existing_notif=notif)
        return
    if field == 'mentions':
        await _start_mention_selection(callback, state, mode='edit', current_mode=notif.get('mention_mode', 'none'))
        return


async def _finalize_new_notification(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_notif = data.get('new_notification')
    if not new_notif:
        await message.answer('Ошибка при создании уведомления. Попробуйте снова.')
        await _send_notifications_menu(message, state)
        return
    weekday_messages = data.get('weekday_messages')
    notif_id = nodb.create_scheduled_notification(
        title=new_notif['title'],
        description=new_notif.get('description', ''),
        message=new_notif['message'],
        time_value=new_notif['time'],
        groups=new_notif['groups'],
        mention_mode=new_notif['mention_mode'],
        manual_mentions=new_notif.get('manual_mentions', ''),
        builtin_key=new_notif.get('builtin_key'),
        enabled=new_notif.get('enabled', True),
        is_one_time=new_notif.get('is_one_time', False),
        weekday_messages=weekday_messages
    )
    await state.update_data(new_notification=None)
    await _send_notifications_menu(message, state, notice=f'Уведомление #{notif_id} создано.')


async def _return_to_edit_menu(target: types.Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    notif = nodb.get_scheduled_notification(notif_id) if notif_id else None
    if notif:
        await _show_notification_edit_menu(target, notif)
        await state.set_state(NotificationStates.edit_choice)


@admin_router.callback_query(F.data.startswith('notif|group|'))
async def notifications_group_toggle(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, gid_str = callback.data.split('|', 3)
    try:
        gid = int(gid_str)
    except ValueError:
        await callback.answer('Некорректная группа', show_alert=True)
        return
    data = await state.get_data()
    selection = data.get('group_selection')
    if not selection or selection.get('mode') != mode:
        await callback.answer('Нет активного выбора групп.', show_alert=True)
        return
    selected = set(selection.get('selected', []))
    if gid in selected:
        selected.remove(gid)
    else:
        selected.add(gid)
    selection['selected'] = sorted(selected)
    await state.update_data(group_selection=selection)
    text = _group_selection_text(selected)
    markup = _group_selection_markup(selected, mode)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|groupdone|'))
async def notifications_group_done(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode = callback.data.split('|', 2)
    data = await state.get_data()
    selection = data.get('group_selection')
    if not selection or selection.get('mode') != mode:
        await callback.answer('Нет активного выбора групп.', show_alert=True)
        return
    selected = selection.get('selected', [])
    if not selected:
        await callback.answer('Выберите хотя бы одну группу.', show_alert=True)
        return
    thread_list = []
    if mode == 'edit':
        notif_id = selection.get('notif_id') or data.get('edit_notification_id')
        existing = nodb.get_scheduled_notification(notif_id) if notif_id else None
        existing_map = {}
        if existing:
            for entry in existing.get('groups', []):
                group_id = entry.get('group_id') if isinstance(entry, dict) else entry
                thread_id = entry.get('thread_id') if isinstance(entry, dict) else None
                if group_id is not None:
                    existing_map[int(group_id)] = thread_id
        for gid in selected:
            # Для Суперы и Дежурства всегда запрашиваем thread_id заново
            if gid in THREADED_GROUPS:
                thread_list.append({'group_id': gid, 'thread_id': None})
            else:
                thread_list.append({'group_id': gid, 'thread_id': existing_map.get(gid)})
    else:
        for gid in selected:
            # Для Суперы и Дежурства всегда запрашиваем thread_id вручную
            if gid in THREADED_GROUPS:
                thread_list.append({'group_id': gid, 'thread_id': None})
            else:
                thread_list.append({'group_id': gid, 'thread_id': None})
    await state.update_data(thread_prompt_list=thread_list, thread_prompt_index=0)
    await callback.message.edit_text('Настраиваем темы для выбранных групп...')
    await _ask_next_thread(callback.message, state, create_flow=(mode == 'create'))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|groupcancel|'))
async def notifications_group_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode = callback.data.split('|', 2)
    await state.update_data(group_selection=None)
    if mode == 'edit':
        await callback.message.edit_text('Изменение групп отменено.')
        await _return_to_edit_menu(callback.message, state)
    else:
        await state.update_data(new_notification=None)
        await callback.message.edit_text('Выбор групп отменён. Создание уведомления остановлено.')
        await _send_notifications_menu(callback, state)


@admin_router.callback_query(F.data.startswith('notif|mentioncancel|'))
async def notifications_mention_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode = callback.data.split('|', 2)
    if mode == 'edit':
        await callback.message.edit_text('Изменение режима упоминаний отменено.')
        await _return_to_edit_menu(callback.message, state)
    else:
        await state.update_data(new_notification=None)
        await callback.message.edit_text('Создание уведомления отменено.')
        await _send_notifications_menu(callback, state)


@admin_router.callback_query(F.data.startswith('notif|mention|'))
async def notifications_mention_choice(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, mode, value = callback.data.split('|', 3)
    if mode == 'edit':
        notif_id = (await state.get_data()).get('edit_notification_id')
        if not notif_id:
            await callback.answer('Уведомление не найдено', show_alert=True)
            return
        if value == 'manual':
            # Обновляем режим упоминаний на 'manual' в БД
            nodb.update_scheduled_notification(notif_id, mention_mode='manual')
            await callback.message.answer('Введите упоминания вручную (например, "@user1 @user2"). Для отмены напишите "назад":')
            await state.set_state(NotificationStates.edit_manual_mentions)
            await callback.answer()
            return
        nodb.update_scheduled_notification(notif_id, mention_mode=value, manual_mentions='')
        await callback.message.edit_text('Режим упоминаний обновлён.')
        await _return_to_edit_menu(callback.message, state)
        await callback.answer()
    else:
        data = await state.get_data()
        new_notif = data.get('new_notification', {})
        new_notif['mention_mode'] = value
        if value == 'manual':
            await state.update_data(new_notification=new_notif)
            await callback.message.answer('Введите упоминания вручную (например, "@user1 @user2"). Для отмены напишите "отмена":')
            await state.set_state(NotificationStates.create_manual_mentions)
            await callback.answer()
            return
        new_notif['manual_mentions'] = ''
        await state.update_data(new_notification=new_notif)
        await callback.message.edit_text('Режим упоминаний выбран.')
        await _finalize_new_notification(callback.message, state)
        await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|delete|'))
async def notifications_delete_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, notif_id_str = callback.data.split('|', 2)
    try:
        notif_id = int(notif_id_str)
    except ValueError:
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, удалить', callback_data=f'notif|deleteconfirm|{notif_id}')
    builder.button(text='⬅️ Назад', callback_data=f'notif|edit|{notif_id}')
    await callback.message.edit_text('Удалить это уведомление?', reply_markup=builder.adjust(1).as_markup())
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|preview|'))
async def notifications_preview_weekday(callback: CallbackQuery, state: FSMContext):
    """Предпросмотр уведомления с текстами по дням недели."""
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, notif_id_str = callback.data.split('|', 2)
    try:
        notif_id = int(notif_id_str)
    except ValueError:
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    
    weekday_messages = notif.get('weekday_messages')
    if not weekday_messages:
        await callback.answer('Это уведомление не содержит текстов по дням недели', show_alert=True)
        return
    
    base_text = notif.get('message', '')
    mention_mode = notif.get('mention_mode', 'none')
    manual_mentions = notif.get('manual_mentions', '').strip()
    
    # Формируем предпросмотр для каждого дня недели
    preview_text = f"📋 Предпросмотр уведомления #{notif_id} — {notif.get('title', 'Без названия')}\n\n"
    preview_text += "=" * 50 + "\n\n"
    
    for day_name in WEEKDAY_NAMES:
        day_text = weekday_messages.get(day_name)
        
        # Формируем полный текст для этого дня
        full_text = base_text
        if day_text:
            full_text = f"{base_text}\n\n{day_text}"
        
        # Добавляем упоминания если есть
        if mention_mode == 'manual' and manual_mentions:
            full_text = f"{full_text}\n\n{manual_mentions}"
        elif mention_mode == 'duty_auto':
            full_text = f"{full_text}\n\n[Будут упомянуты дежурные по расписанию]"
        
        preview_text += f"📅 {day_name}:\n"
        preview_text += f"{full_text}\n\n"
        preview_text += "=" * 50 + "\n\n"
    
    # Добавляем кнопку возврата
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад', callback_data=f'notif|edit|{notif_id}')
    
    # Разбиваем на части если текст слишком длинный (Telegram лимит ~4096 символов)
    if len(preview_text) > 4000:
        # Отправляем первую часть
        await callback.message.edit_text(preview_text[:4000], reply_markup=builder.as_markup())
        # Отправляем остальное отдельными сообщениями
        remaining = preview_text[4000:]
        while len(remaining) > 4000:
            await callback.message.answer(remaining[:4000])
            remaining = remaining[4000:]
        if remaining:
            await callback.message.answer(remaining)
    else:
        await callback.message.edit_text(preview_text, reply_markup=builder.as_markup())
    
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|deleteconfirm|'))
async def notifications_delete_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, notif_id_str = callback.data.split('|', 2)
    try:
        notif_id = int(notif_id_str)
    except ValueError:
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    nodb.delete_scheduled_notification(notif_id)
    await _send_notifications_menu(callback, state, notice='Уведомление удалено.')


@admin_router.callback_query(F.data.startswith('notif|type|create|'))
async def notifications_type_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, _, type_str = callback.data.split('|')
    
    # Если выбрана рассылка - переходим к вводу текста рассылки
    if type_str == 'broadcast':
        await callback.message.edit_text('Тип выбран: Рассылка')
        await callback.message.answer('Введите текст для рассылки всем пользователям:')
        await state.set_state(NotificationStates.create_broadcast_text)
        await callback.answer()
        return
    
    # Если выбран тип с текстами по дням недели
    if type_str == 'weekday':
        await callback.message.edit_text('Тип выбран: С текстами по дням недели')
        data = await state.get_data()
        new_notif = data.get('new_notification', {})
        new_notif['is_one_time'] = False
        new_notif['is_weekday_variable'] = True
        await state.update_data(new_notification=new_notif, weekday_messages={}, weekday_current_day=0)
        # Для weekday уведомлений тоже нужны title и description
        await callback.message.answer('Введите название уведомления:')
        await state.set_state(NotificationStates.create_title)
        await callback.answer()
        return
    
    # Для обычных уведомлений (Повторяющееся/Одноразовое)
    is_one_time = type_str == '1'
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    new_notif['is_one_time'] = is_one_time
    await state.update_data(new_notification=new_notif)
    await callback.message.edit_text(f'Тип выбран: {"Одноразовое" if is_one_time else "Повторяющееся"}')
    # Для обычных уведомлений запрашиваем название
    await callback.message.answer('Введите название уведомления:')
    await state.set_state(NotificationStates.create_title)
    await callback.answer()


@admin_router.callback_query(NotificationStates.create_one_time_month)
async def notifications_one_time_month(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    month = callback.data
    await state.update_data(one_time_month=month)
    await callback.message.edit_text('Выберите дату', reply_markup=await calendar_day(month))
    await state.set_state(NotificationStates.create_one_time_day)
    await callback.answer()


@admin_router.callback_query(NotificationStates.create_one_time_day)
async def notifications_one_time_day(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    day = callback.data
    if day == 'назад':
        await callback.message.edit_text('Выберите месяц', reply_markup=await calendar_month())
        await state.set_state(NotificationStates.create_one_time_month)
        await callback.answer()
        return
    await state.update_data(one_time_day=day)
    data = await state.get_data()
    month = data['one_time_month']
    day = data['one_time_day']
    if int(day) < 10:
        day = '0' + day
    months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
              'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
    month_num = str(months.index(month) + 1)
    if int(month_num) < 10:
        month_num = '0' + month_num
    date_str = day + '.' + month_num
    await callback.message.edit_text('Выберите время', reply_markup=await calendar_time(date_str))
    await state.set_state(NotificationStates.create_one_time_time)
    await callback.answer()


@admin_router.callback_query(NotificationStates.create_one_time_time)
async def notifications_one_time_time(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    time_value = callback.data
    if time_value == 'назад':
        data = await state.get_data()
        month = data['one_time_month']
        await callback.message.edit_text('Выберите дату', reply_markup=await calendar_day(month))
        await state.set_state(NotificationStates.create_one_time_day)
        await callback.answer()
        return
    data = await state.get_data()
    month = data['one_time_month']
    day = data['one_time_day']
    if int(day) < 10:
        day = '0' + day
    months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
              'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
    month_num = str(months.index(month) + 1)
    if int(month_num) < 10:
        month_num = '0' + month_num
    # Формируем расписание в формате date=MM-DD HH:MM
    schedule = f"date={month_num}-{day} {time_value}"
    new_notif = data.get('new_notification', {})
    new_notif['time'] = schedule
    await state.update_data(new_notification=new_notif)
    await callback.message.edit_text(f'Дата и время выбраны: {day}.{month_num} {time_value}')
    # Переходим к выбору групп
    await _start_group_selection(callback, state, mode='create')
    await callback.answer()


@admin_router.callback_query(F.data.startswith('notif|toggle|'))
async def notifications_toggle_enabled(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, notif_id_str = callback.data.split('|', 2)
    try:
        notif_id = int(notif_id_str)
    except ValueError:
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    new_enabled = not notif.get('enabled', True)
    nodb.update_scheduled_notification(notif_id, enabled=new_enabled)
    notif['enabled'] = new_enabled
    await _show_notification_edit_menu(callback, notif)
    await callback.answer('Статус обновлен')


@admin_router.callback_query(F.data.startswith('notif|toggletime|'))
async def notifications_toggle_one_time(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    _, _, notif_id_str = callback.data.split('|', 2)
    try:
        notif_id = int(notif_id_str)
    except ValueError:
        await callback.answer('Некорректный идентификатор', show_alert=True)
        return
    notif = nodb.get_scheduled_notification(notif_id)
    if not notif:
        await callback.answer('Уведомление не найдено', show_alert=True)
        return
    new_is_one_time = not notif.get('is_one_time', False)
    nodb.update_scheduled_notification(notif_id, is_one_time=new_is_one_time)
    notif['is_one_time'] = new_is_one_time
    await _show_notification_edit_menu(callback, notif)
    await callback.answer('Тип обновлен')


@admin_router.callback_query(F.data == 'notif|createcancel')
async def notifications_create_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    await state.update_data(new_notification=None)
    await _send_notifications_menu(callback, state, notice='Создание уведомления отменено.')
    await callback.answer()


@admin_router.message(NotificationStates.create_title)
async def notifications_create_title(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state, 'Создание уведомления отменено.')
        return
    if not text:
        await message.answer('Название не может быть пустым. Введите название уведомления:')
        return
    new_notif = (await state.get_data()).get('new_notification') or {}
    new_notif['title'] = text
    await state.update_data(new_notification=new_notif)
    await message.answer('Введите описание уведомления:')
    await state.set_state(NotificationStates.create_description)


@admin_router.message(NotificationStates.create_description)
async def notifications_create_description(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state, 'Создание уведомления отменено.')
        return
    new_notif = (await state.get_data()).get('new_notification') or {}
    new_notif['description'] = text
    await state.update_data(new_notification=new_notif)
    
    # Проверяем, является ли это уведомлением типа weekday
    if new_notif.get('is_weekday_variable'):
        # Для weekday уведомлений переходим к вводу основного текста
        await message.answer('Введите основной текст уведомления (будет использоваться для всех дней):')
        await state.set_state(NotificationStates.create_weekday_base_text)
    else:
        # Для обычных уведомлений переходим к вводу текста
        await message.answer('Введите текст уведомления:')
        await state.set_state(NotificationStates.create_text)


def _extract_mentions_from_message(message: types.Message) -> str:
    """Извлекает упоминания из entities сообщения."""
    if not message.entities:
        return ''
    mentions = []
    for entity in message.entities:
        if entity.type == 'mention':
            # Извлекаем текст упоминания из сообщения
            start = entity.offset
            end = start + entity.length
            mention_text = message.text[start:end] if message.text else ''
            if mention_text and mention_text not in mentions:
                mentions.append(mention_text)
        elif entity.type == 'text_mention' and entity.user:
            # Для text_mention используем username или first_name
            username = entity.user.username
            if username:
                mention_text = f'@{username}'
            else:
                mention_text = f'@{entity.user.first_name}'
            if mention_text not in mentions:
                mentions.append(mention_text)
    return ' '.join(mentions)


@admin_router.message(NotificationStates.create_text)
async def notifications_create_text(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state, 'Создание уведомления отменено.')
        return
    if not text:
        await message.answer('Текст не может быть пустым. Введите текст уведомления:')
        return
    
    # Сохраняем текст как есть, не трогая упоминания в тексте
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    new_notif['message'] = text
    
    await state.update_data(new_notification=new_notif)
    # После ввода текста переходим к выбору расписания (тип уже выбран ранее)
    is_one_time = new_notif.get('is_one_time', False)
    if is_one_time:
        # Для одноразовых уведомлений сразу запрашиваем дату
        await message.answer('Выберите месяц', reply_markup=await calendar_month())
        await state.set_state(NotificationStates.create_one_time_month)
    else:
        # Для повторяющихся уведомлений выбираем тип расписания
        await _start_schedule_selection(message, state, mode='create')


@admin_router.message(NotificationStates.create_time)
async def notifications_create_time(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state)
        return
    normalized = _normalize_time_string(text)
    if not normalized:
        await message.answer(
            'Неверный формат. Примеры: 10:00, mon 10:00, day=6 10:00, last 10:00, date=08-23 09:00.'
        )
        return
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    new_notif['time'] = normalized
    await state.update_data(new_notification=new_notif)
    groups_prompt = (
        "Выберите группы, в которые будет отправляться уведомление. Укажите номера через пробел.\n"
        f"{_notification_groups_text()}\n"
        "Например: '1 3'. Для выбора всех групп напишите 'все'. Чтобы отменить создание, отправьте 'отмена'."
    )
    await message.answer(groups_prompt)
    await state.set_state(NotificationStates.create_groups)


@admin_router.message(NotificationStates.create_groups)
async def notifications_create_groups(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state)
        return
    groups = _parse_group_selection(text)
    if not groups:
        await message.answer('Не удалось распознать выбор. Укажите номера групп через пробел (например, "1 3") или "все":')
        return
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    thread_list = [{'group_id': gid, 'thread_id': None} for gid in groups]
    await state.update_data(new_notification=new_notif, thread_prompt_list=thread_list, thread_prompt_index=0)
    await _ask_next_thread(message, state, create_flow=True)


@admin_router.message(NotificationStates.create_mention_mode)
async def notifications_create_mention_mode(message: types.Message, state: FSMContext):
    text = (message.text or '').strip().lower()
    if text == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state)
        return
    mapping = {
        '1': 'none', 'нет': 'none', 'без': 'none', '0': 'none',
        '2': 'duty_auto', 'дежур': 'duty_auto', 'дежурных': 'duty_auto',
        '3': 'manual', 'ручн': 'manual', 'вручную': 'manual'
    }
    mode = mapping.get(text)
    if not mode:
        await message.answer('Введите 1, 2 или 3 (или "отмена" для отмены):')
        return
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    new_notif['mention_mode'] = mode
    if mode == 'manual':
        await state.update_data(new_notification=new_notif)
        await message.answer('Введите упоминания вручную (например, "@user1 @user2"). Для отмены напишите "отмена":')
        await state.set_state(NotificationStates.create_manual_mentions)
        return
    new_notif['manual_mentions'] = ''
    await state.update_data(new_notification=new_notif)
    await _finalize_new_notification(message, state)


@admin_router.message(NotificationStates.create_broadcast_text)
async def notifications_create_broadcast_text(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state, 'Создание рассылки отменено.')
        return
    if not text:
        await message.answer('Текст не может быть пустым. Введите текст для рассылки:')
        return
    # Запрашиваем подтверждение
    await state.update_data(broadcast_text=text)
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Да, отправить', callback_data='notif|broadcast_direct_confirm')
    builder.button(text='❌ Отмена', callback_data='notif|createcancel')
    await message.answer(
        f'Подтвердите отправку рассылки:\n\n'
        f'Текст: {text[:200]}{"..." if len(text) > 200 else ""}\n\n'
        f'Сообщение будет отправлено всем зарегистрированным пользователям в личные сообщения.\n'
        f'Отправка будет происходить с задержкой, чтобы не перегружать сервер.',
        reply_markup=builder.adjust(1).as_markup()
    )


@admin_router.callback_query(F.data == 'notif|broadcast_direct_confirm')
async def notifications_broadcast_direct_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    data = await state.get_data()
    broadcast_text = data.get('broadcast_text')
    if not broadcast_text:
        await callback.answer('Текст рассылки не найден', show_alert=True)
        return
    user_ids = udb.list_all_users()
    if not user_ids:
        await callback.message.edit_text('Нет пользователей для рассылки.')
        await callback.answer()
        await state.update_data(new_notification=None, broadcast_text=None)
        await _send_notifications_menu(callback.message, state)
        return
    await callback.message.edit_text(f'Начинаю рассылку {len(user_ids)} пользователям...')
    await callback.answer()
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            message_with_label = f"🔔 Уведомление\n\n{broadcast_text}"
            await bot.send_message(user_id, message_with_label)
            sent += 1
            # Задержка 0.1 секунды между сообщениями, чтобы не перегружать сервер
            await asyncio.sleep(0.1)
        except Exception as e:
            failed += 1
            print(f'Ошибка отправки пользователю {user_id}: {e}')
    await callback.message.answer(
        f'Рассылка завершена!\n'
        f'Отправлено: {sent}\n'
        f'Ошибок: {failed}',
        reply_markup=InlineKeyboardBuilder().button(text='⬅️ В меню', callback_data='notif|menu').adjust(1).as_markup()
    )
    await state.update_data(new_notification=None, broadcast_text=None)
    await _send_notifications_menu(callback.message, state)


@admin_router.message(NotificationStates.create_manual_mentions)
async def notifications_create_manual_mentions(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None)
        await _send_notifications_menu(message, state)
        return
    
    # Извлекаем упоминания из entities сообщения
    extracted_mentions = _extract_mentions_from_message(message)
    
    # Если есть упоминания в entities, используем их, иначе используем текст как есть
    if extracted_mentions:
        final_mentions = extracted_mentions
    else:
        # Если упоминаний в entities нет, но в тексте есть @, используем текст
        # Проверяем, есть ли в тексте упоминания через регулярное выражение
        mention_pattern = r'@\w+'
        found_mentions = re.findall(mention_pattern, text)
        if found_mentions:
            final_mentions = ' '.join(found_mentions)
        else:
            final_mentions = text
    
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    new_notif['manual_mentions'] = final_mentions
    await state.update_data(new_notification=new_notif)
    await _finalize_new_notification(message, state)


@admin_router.message(NotificationStates.edit_choice)
async def notifications_edit_choice(message: types.Message, state: FSMContext):
    await message.answer('Используйте кнопки под сообщением для редактирования уведомления.')


@admin_router.message(NotificationStates.edit_title)
async def notifications_edit_title(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    nodb.update_scheduled_notification(notif_id, title=text)
    await message.answer('Название обновлено.')
    await _return_to_edit_menu(message, state)


@admin_router.message(NotificationStates.edit_description)
async def notifications_edit_description(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    nodb.update_scheduled_notification(notif_id, description=text)
    await message.answer('Описание обновлено.')
    await _return_to_edit_menu(message, state)


@admin_router.message(NotificationStates.edit_text)
async def notifications_edit_text(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    
    # Сохраняем текст как есть, не трогая упоминания в тексте
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    nodb.update_scheduled_notification(notif_id, message=text)
    
    await message.answer('Текст обновлён.')
    await _return_to_edit_menu(message, state)


@admin_router.message(NotificationStates.edit_time)
async def notifications_edit_time(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    normalized = _normalize_time_string(text)
    if not normalized:
        await message.answer(
            'Неверный формат. Примеры: 10:00, mon 10:00, day=6 10:00, last 10:00, date=08-23 09:00.'
        )
        return
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    nodb.update_scheduled_notification(notif_id, time=normalized)
    await message.answer('Время обновлено.')
    await _return_to_edit_menu(message, state)


@admin_router.message(NotificationStates.edit_groups)
async def notifications_edit_groups(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    groups = _parse_group_selection(text)
    if not groups:
        await message.answer('Не удалось распознать выбор. Укажите номера групп через пробел (например, "1 3") или "все":')
        return
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    existing = nodb.get_scheduled_notification(notif_id) if notif_id else None
    existing_map = {}
    if existing:
        for entry in existing.get('groups', []):
            if isinstance(entry, dict):
                existing_map[int(entry.get('group_id'))] = entry.get('thread_id')
    thread_list = []
    for gid in groups:
        thread_list.append({
            'group_id': gid,
            'thread_id': existing_map.get(gid)
        })
    await state.update_data(thread_prompt_list=thread_list, thread_prompt_index=0)
    await _ask_next_thread(message, state, create_flow=False)


@admin_router.message(NotificationStates.edit_mention_mode)
async def notifications_edit_mention_mode(message: types.Message, state: FSMContext):
    text = (message.text or '').strip().lower()
    if text in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    mapping = {
        '1': 'none', 'нет': 'none', 'без': 'none', '0': 'none',
        '2': 'duty_auto', 'дежур': 'duty_auto', 'дежурных': 'duty_auto',
        '3': 'manual', 'ручн': 'manual', 'вручную': 'manual'
    }
    mode = mapping.get(text)
    if not mode:
        await message.answer('Введите 1, 2 или 3 (или "назад" для отмены):')
        return
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    nodb.update_scheduled_notification(notif_id, mention_mode=mode)
    if mode == 'manual':
        await message.answer('Введите упоминания вручную (например, "@user1 @user2"). Для отмены напишите "назад":')
        await state.set_state(NotificationStates.edit_manual_mentions)
    else:
        nodb.update_scheduled_notification(notif_id, manual_mentions='')
        await message.answer('Тип упоминаний обновлён.')
        await _return_to_edit_menu(message, state)


@admin_router.message(NotificationStates.edit_manual_mentions)
async def notifications_edit_manual_mentions(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() in {'назад', 'отмена'}:
        await _return_to_edit_menu(message, state)
        return
    
    # Извлекаем упоминания из entities сообщения
    extracted_mentions = _extract_mentions_from_message(message)
    
    # Если есть упоминания в entities, используем их, иначе используем текст как есть
    if extracted_mentions:
        final_mentions = extracted_mentions
    else:
        # Если упоминаний в entities нет, но в тексте есть @, используем текст
        # Проверяем, есть ли в тексте упоминания через регулярное выражение
        mention_pattern = r'@\w+'
        found_mentions = re.findall(mention_pattern, text)
        if found_mentions:
            final_mentions = ' '.join(found_mentions)
        else:
            final_mentions = text
    
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    # Обновляем упоминания и убеждаемся, что режим установлен на 'manual'
    nodb.update_scheduled_notification(notif_id, mention_mode='manual', manual_mentions=final_mentions)
    await message.answer('Упоминания обновлены.')
    await _return_to_edit_menu(message, state)


@admin_router.message(NotificationStates.delete_confirm)
async def notifications_delete_confirm(message: types.Message, state: FSMContext):
    text = (message.text or '').strip().lower()
    data = await state.get_data()
    notif_id = data.get('edit_notification_id')
    if text in {'да', 'yes', 'y'}:
        if notif_id:
            nodb.delete_scheduled_notification(notif_id)
            await message.answer('Уведомление удалено.')
        await state.update_data(edit_notification_id=None)
        await _send_notifications_menu(message, state)
        return
    if text in {'нет', 'no', 'n', 'назад'}:
        await _return_to_edit_menu(message, state)
        return
    await message.answer('Введите "Да" или "Нет":')


def _employment_label(code: str | None) -> str:
    if code == 'СЗ':
        return 'Самозанятый'
    if code == 'ИП':
        return 'ИП'
    return 'Не указан'


def _format_trainer_details(details: dict, include_header: bool = True) -> str:
    nickname = details.get('nickname') or '—'
    username = details.get('username')
    header = f"#{details.get('id')} {nickname}"
    if username:
        header += f" (@{username})"
    lines = []
    if include_header:
        lines.append(header)
    lines.extend([
        f"Телефон: {details.get('phone') or '—'}",
        f"Email: {details.get('email') or '—'}",
        f"Дата рождения: {details.get('birthday') or '—'}",
        f"Статус занятости: {_employment_label(details.get('employment_type'))}",
        f"Медкомиссия: {details.get('med_date') or '—'}",
        f"Повышение квалификации: {details.get('qual_date') or '—'}",
    ])
    # Добавляем статус поздравлений с ДР
    birthday_disabled = details.get('birthday_notifications_disabled', False)
    birthday_status = '❌ Отключены' if birthday_disabled else '✅ Включены'
    lines.append(f"Поздравления с ДР: {birthday_status}")
    return '\n'.join(lines)


def _build_trainer_overview_text(trainers: list[tuple[int, str, str]]) -> str:
    blocks = []
    for trainer_id, _, _ in trainers:
        details = udb.get_trainer_details(trainer_id)
        if not details:
            continue
        blocks.append(_format_trainer_details(details))
    if not blocks:
        return 'Данные тренеров пока не заполнены.'
    return 'Данные тренеров:\n\n' + '\n\n'.join(blocks)


def _trainer_select_keyboard(trainers: list[tuple[int, str, str]], page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    total = len(trainers)
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total)
    page_trainers = trainers[start_idx:end_idx]
    
    rows = []
    row: list[InlineKeyboardButton] = []
    for trainer_id, name, _ in page_trainers:
        label = name or f'#{trainer_id}'
        row.append(InlineKeyboardButton(text=label[:32], callback_data=f"tr_sel:{trainer_id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    
    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text='⬅️ Назад', callback_data=f'tr_page:{page-1}'))
    if end_idx < total:
        nav_buttons.append(InlineKeyboardButton(text='Вперёд ➡️', callback_data=f'tr_page:{page+1}'))
    if nav_buttons:
        rows.append(nav_buttons)
    
    rows.append([InlineKeyboardButton(text='Обновить список', callback_data='tr_refresh')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _trainer_fields_keyboard(trainer_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for label, field_key in TRAINER_FIELDS:
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"tr_field:{trainer_id}:{field_key}")])
    
    # Кнопка для отключения/включения поздравлений с днем рождения
    details = udb.get_trainer_details(trainer_id)
    birthday_disabled = details.get('birthday_notifications_disabled', False) if details else False
    button_text = '❌ Отключить поздравления с ДР' if not birthday_disabled else '✅ Включить поздравления с ДР'
    buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"tr_birthday_toggle:{trainer_id}")])
    
    buttons.append([InlineKeyboardButton(text='⬅️ К списку', callback_data='tr_back')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _sync_trainer_registration(trainer_id: int):
    if not sheets_service or not sheets_service.is_available():
        return
    details = udb.get_trainer_details(trainer_id)
    if not details:
        return
    full_name = details.get('nickname')
    if not full_name:
        return
    try:
        await sheets_service.sync_user_registration({
            'full_name': full_name,
            'phone': details.get('phone') or '',
            'birthday': details.get('birthday') or '',
            'employment_type': details.get('employment_type') or '',
            'email': details.get('email') or '',
        })
    except Exception as e:
        print(f'Error syncing trainer registration: {e}')


def _normalize_sheet_date(value: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ('%d.%m.%Y', '%d.%m.%y'):
        try:
            parsed = datetime.strptime(value, fmt)
            year = parsed.year
            if year < 100:
                year += 2000
            parsed = parsed.replace(year=year)
            return parsed.strftime('%d.%m.%Y')
        except ValueError:
            continue
    return None


def _parse_date_or_none(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%d.%m.%Y').date()
    except (ValueError, TypeError):
        return None


def _format_date(date_obj: date) -> str:
    return date_obj.strftime('%d.%m.%Y')


def _trainer_link(details: dict) -> str:
    nickname = html.escape(details.get('nickname') or 'тренер')
    username = details.get('username')
    user_id = details.get('user_id')
    if username:
        return f'@{username}'
    if user_id:
        return f'<a href="tg://user?id={user_id}">{nickname}</a>'
    return nickname


def _apply_sheet_records(records: list[tuple[str, str]] | None, record_type: str):
    if not records:
        return
    for name, date_value in records:
        trainer_id = udb.get_trainer_id_by_name(name.strip())
        if not trainer_id:
            continue
        normalized = _normalize_sheet_date(date_value)
        if not normalized:
            continue
        details = udb.get_trainer_details(trainer_id)
        current = details.get('med_date' if record_type == 'med' else 'qual_date')
        if current == normalized:
            continue
        if record_type == 'med':
            udb.set_med_date(trainer_id, normalized)
        else:
            udb.set_qual_date(trainer_id, normalized)


def _apply_email_records(records: list[tuple[str, str]] | None):
    """Синхронизирует email из Google Sheets в БД."""
    if not records:
        return
    for name, email_value in records:
        trainer_id = udb.get_trainer_id_by_name(name.strip())
        if not trainer_id:
            continue
        email = email_value.strip() if email_value else ''
        # Валидация email
        if email and not EMAIL_REGEX.fullmatch(email):
            continue
        details = udb.get_trainer_details(trainer_id)
        current_email = details.get('email') or ''
        if current_email == email:
            continue
        # Обновляем email в БД
        udb.update_trainer_field(trainer_id, 'email', email)


async def sync_trainer_sheet_data(bot: Bot | None = None):
    if not sheets_service or not sheets_service.is_available():
        return
    loop = asyncio.get_event_loop()
    try:
        med_records = await asyncio.wait_for(
            loop.run_in_executor(None, sheets_service.fetch_medical_records), timeout=30
        )
        _apply_sheet_records(med_records, 'med')
        qual_records = await asyncio.wait_for(
            loop.run_in_executor(None, sheets_service.fetch_qualification_records), timeout=30
        )
        _apply_sheet_records(qual_records, 'qual')
        email_records = await asyncio.wait_for(
            loop.run_in_executor(None, sheets_service.fetch_user_emails), timeout=30
        )
        _apply_email_records(email_records)
    except asyncio.TimeoutError:
        logger.error('sync_trainer_sheet_data: превышен таймаут 30с при обращении к Google Sheets')
    except Exception as e:
        logger.error(f'sync_trainer_sheet_data: ошибка — {e}')


async def notify_trainer_expirations(bot: Bot):
    today = date.today()
    trainers = udb.list_trainers()
    for trainer_id, _, _ in trainers:
        details = udb.get_trainer_details(trainer_id)
        link = _trainer_link(details)
        med_date = _parse_date_or_none(details.get('med_date'))
        if med_date:
            due_date = med_date + timedelta(days=365)
            due_str = _format_date(due_date)
            if today >= due_date and details.get('med_last_notified') != due_str:
                text = f"⚕️ У {link} истек срок медкомиссии ({details.get('med_date')})."
                try:
                    await bot.send_message(SUPERS_GROUP_ID, text, message_thread_id=1)
                    udb.set_med_notified(trainer_id, due_str)
                except Exception as e:
                    print(f'Ошибка отправки напоминания о медкомиссии: {e}')
        qual_date = _parse_date_or_none(details.get('qual_date'))
        if qual_date:
            due_date = qual_date + timedelta(days=365 * 2)
            due_str = _format_date(due_date)
            if today >= due_date and details.get('qual_last_notified') != due_str:
                text = f"📚 У {link} истек срок повышения квалификации ({details.get('qual_date')})."
                try:
                    await bot.send_message(SUPERS_GROUP_ID, text, message_thread_id=1)
                    udb.set_qual_notified(trainer_id, due_str)
                except Exception as e:
                    print(f'Ошибка отправки напоминания о квалификации: {e}')




@admin_router.message(F.text=='Удалить тренера')
async def delete_trainer_menu(message: types.Message):
    if message.from_user.id not in admins:
        return
    trainers = udb.list_trainers()
    if not trainers:
        await message.answer('Список тренеров пуст.', reply_markup=trener_kb)
        return
    # Формируем текстовый список
    text_lines = [f"#{tid}: {name} (@{uname})" for tid, name, uname in trainers]
    text = 'Список тренеров:\n' + '\n'.join(text_lines) + '\n\nВыберите кого удалить:'
    # Формируем инлайн-кнопки (сортируем по номеру тренера)
    rows = []
    row = []
    for idx, (tid, name, uname) in enumerate(sorted(trainers, key=lambda x: x[0]), start=1):
        row.append(InlineKeyboardButton(text=f"Удалить #{tid}", callback_data=f"del_tr_{tid}"))
        if idx % 2 == 0:  # две кнопки в ряд
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith('del_tr_'))
async def delete_trainer_cb(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        trainer_id = int(callback.data.replace('del_tr_', ''))
    except ValueError:
        await callback.answer('Некорректный ID', show_alert=True)
        return
    
    # Get trainer details before deletion
    trainer_details = udb.get_trainer_details(trainer_id)
    if not trainer_details:
        await callback.answer('Тренер не найден', show_alert=True)
        return
    
    trainer_name = trainer_details.get('nickname')
    trainer_user_id = trainer_details.get('user_id')
    
    # Группы для удаления (те же, что используются при регистрации)
    registration_groups = {
        'Дежурства': DUTY_GROUP_ID,
        'Важное': IMPORTANT_GROUP_ID,
        'Кроме работы': WORK_BDAY_GROUP_ID,
        'Общаяя': COMMON_GROUP_ID,
    }
    
    # Удаляем пользователя из всех групп
    removed_from_groups = []
    failed_groups = []
    
    if trainer_user_id:
        from datetime import datetime, timedelta
        # Используем until_date в прошлом (1 секунда назад) для немедленного удаления
        until_date = datetime.utcnow() - timedelta(seconds=1)
        
        for group_name, group_id in registration_groups.items():
            try:
                # Баним пользователя с until_date в прошлом - это удалит его из группы
                await bot.ban_chat_member(
                    chat_id=group_id,
                    user_id=trainer_user_id,
                    until_date=until_date,
                    revoke_messages=False  # Не удаляем сообщения
                )
                removed_from_groups.append(group_name)
                logger.info(f'Пользователь {trainer_user_id} удален из группы {group_name} (ID: {group_id})')
            except Exception as e:
                failed_groups.append(group_name)
                logger.error(f'Ошибка удаления пользователя {trainer_user_id} из группы {group_name} (ID: {group_id}): {e}', exc_info=True)
    
    # Удаляем из базы данных
    udb.delete_user_by_id(trainer_id)
    
    # Sync deletion to Google Sheets
    if sheets_service and sheets_service.is_available() and trainer_name:
        try:
            sheets_service.delete_trainer_from_sheets(trainer_name)
        except Exception as e:
            logger.error(f"Error syncing trainer deletion to Sheets: {e}", exc_info=True)
    
    # Формируем сообщение о результате
    result_text = 'Тренер удален.'
    if removed_from_groups:
        result_text += f'\nУдален из групп: {", ".join(removed_from_groups)}'
    if failed_groups:
        result_text += f'\nОшибки при удалении из групп: {", ".join(failed_groups)}'
    
    await callback.answer('Удалено')
    await callback.message.edit_text(result_text)


def _format_schedule_text() -> str:
    qdb.ensure_defaults()
    trainers_map = {tid: (name, uname) for tid, name, uname in udb.list_trainers()}
    lines = []
    for day, windows in WEEKDAY_WINDOWS.items():
        lines.append(f'\n<b>{day}</b>')
        for w in windows:
            trainer_ids = qdb.get_trainers_for(day, w)
            if not trainer_ids:
                label = 'нет тренера'
            else:
                parts = []
                for tid in trainer_ids[:2]:
                    name_un = trainers_map.get(tid)
                    if not name_un:
                        continue
                    name, uname = name_un
                    parts.append(f'{name} (@{uname})')
                label = ', '.join(parts) if parts else 'нет тренера'
            lines.append(f'{w}: {label}')
    return '\n'.join(lines)


@admin_router.message(F.text=='Изменить очередь')
async def queue_menu(message: types.Message, state: FSMContext):
    if message.from_user.id not in admins:
        return
    qdb.ensure_defaults()
    text = 'Текущее расписание:' + '\n' + _format_schedule_text()
    await message.answer(text, reply_markup=queue_days_kb)
    await state.set_state(QueueAssign.day)


@admin_router.message(QueueAssign.day)
async def queue_select_day(message: types.Message, state: FSMContext):
    day = message.text.strip()
    if day not in WEEKDAY_WINDOWS:
        await message.answer('Выберите день недели из клавиатуры.', reply_markup=queue_days_kb)
        return
    await state.update_data(day=day)
    # Сформировать клавиатуру окон времени
    windows = WEEKDAY_WINDOWS[day]
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    rows = []
    row = []
    for idx, w in enumerate(windows, start=1):
        row.append(KeyboardButton(text=w))
        if idx % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(text='Главное меню')])
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    await message.answer('Выберите окно времени', reply_markup=kb)
    await state.set_state(QueueAssign.window)


@admin_router.message(QueueAssign.window)
async def queue_select_window(message: types.Message, state: FSMContext):
    data = await state.get_data()
    day = data['day']
    win = message.text.strip()
    if win not in WEEKDAY_WINDOWS[day]:
        await message.answer('Выберите окно времени из клавиатуры.')
        return
    await state.update_data(window=win)
    trainers = udb.list_trainers()
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    rows = []
    row = []
    if trainers:
        for idx, (tid, name, uname) in enumerate(trainers, start=1):
            row.append(KeyboardButton(text=f'#{tid} {name} (@{uname})'))
            if idx % 1 == 0:
                rows.append(row)
                row = []
    if row:
        rows.append(row)
    # Кнопки удаления тренеров из выбранного окна
    existing = qdb.get_trainers_for(day, win)
    if existing:
        trainer_map = {tid: (name, uname) for tid, name, uname in trainers}
        for tid in existing[:2]:
            name, uname = trainer_map.get(tid, (f'ID {tid}', 'unknown'))
            rows.append([KeyboardButton(text=f'Удалить #{tid} {name} (@{uname})')])
        rows.append([KeyboardButton(text='Очистить окно')])
    rows.append([KeyboardButton(text='Главное меню')])
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    await message.answer('Выберите тренера или действие удаления', reply_markup=kb)
    await state.set_state(QueueAssign.trainer)


@admin_router.message(QueueAssign.trainer)
async def queue_select_trainer(message: types.Message, state: FSMContext):
    text = message.text.strip()
    # Явный выход в меню
    if text == 'Главное меню':
        await state.clear()
        await message.answer('Перевожу вас в меню тренеров.', reply_markup=trener_kb)
        return
    # Удаление одного тренера
    if text.startswith('Удалить #'):
        parts = text.split()
        try:
            trainer_id = int(parts[1].replace('#',''))
        except Exception:
            await message.answer('Некорректный выбор при удалении.')
            return
        data = await state.get_data()
        day = data['day']
        win = data['window']
        qdb.remove_trainer_from_slot(day, win, trainer_id)
        await message.answer('Тренер удален из окна. Обновленное расписание:')
        await message.answer(_format_schedule_text(), reply_markup=trener_kb)
        await state.clear()
        return
    # Полная очистка окна
    if text == 'Очистить окно':
        data = await state.get_data()
        day = data['day']
        win = data['window']
        qdb.clear_slot(day, win)
        await message.answer('Окно очищено. Обновленное расписание:')
        await message.answer(_format_schedule_text(), reply_markup=trener_kb)
        await state.clear()
        return
    # Назначение тренера
    if not text.startswith('#'):
        # Пользователь ничего не выбрал из предложенных — сбрасываем состояние
        await state.clear()
        await message.answer('Действие отменено.', reply_markup=trener_kb)
        return
    try:
        trainer_id = int(text.split()[0].replace('#',''))
    except Exception:
        await message.answer('Некорректный выбор тренера.')
        return
    data = await state.get_data()
    day = data['day']
    win = data['window']
    # Найти id слота
    slots = qdb.list_day(day)
    slot_id = None
    for sid, w, _ in slots:
        if w == win:
            slot_id = sid
            break
    if slot_id is None:
        await message.answer('Слот не найден.')
        await state.clear()
        return
    # Добавим/заменим второго тренера в слоте, ограничиваем максимум 2
    # Стратегия: если меньше 2 — добавим как второго, если уже 2 — заменим второго
    existing = qdb.get_trainers_for(day, win)
    if len(existing) < 2 and trainer_id not in existing:
        qdb.add_trainer_to_slot(day, win, trainer_id)
    else:
        qdb.replace_second_trainer(day, win, trainer_id)
    qdb.ensure_two_limit(day, win)
    await message.answer('Сохранено. Новое расписание:')
    await message.answer(_format_schedule_text(), reply_markup=trener_kb)
    await state.clear()


@admin_router.message(F.text=='Данные тренеров')
async def trainer_data_menu(message: types.Message, state: FSMContext):
    if message.from_user.id not in admins:
        return
    trainers = udb.list_trainers()
    if not trainers:
        await message.answer('Список тренеров пуст.', reply_markup=trener_kb)
        return
    await state.update_data(trainer_list_page=0)
    await message.answer('Выберите тренера для редактирования:', reply_markup=_trainer_select_keyboard(trainers, page=0))
    await state.set_state(TrainerDataStates.select_trainer)


@admin_router.callback_query(F.data=='tr_refresh')
async def trainer_data_refresh(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    trainers = udb.list_trainers()
    if not trainers:
        await callback.message.answer('Список тренеров пуст.', reply_markup=trener_kb)
        await callback.answer()
        return
    await state.update_data(trainer_list_page=0)
    await callback.message.edit_text('Выберите тренера для редактирования:', reply_markup=_trainer_select_keyboard(trainers, page=0))
    await state.set_state(TrainerDataStates.select_trainer)
    await callback.answer('Обновлено')


@admin_router.callback_query(F.data.startswith('tr_page:'))
async def trainer_data_page(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        page = int(callback.data.split(':')[1])
    except (ValueError, IndexError):
        await callback.answer('Некорректная страница', show_alert=True)
        return
    trainers = udb.list_trainers()
    if not trainers:
        await callback.answer('Список тренеров пуст', show_alert=True)
        return
    await state.update_data(trainer_list_page=page)
    await callback.message.edit_text('Выберите тренера для редактирования:', reply_markup=_trainer_select_keyboard(trainers, page=page))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('tr_sel:'))
async def trainer_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        trainer_id = int(callback.data.split(':', maxsplit=1)[1])
    except (ValueError, IndexError):
        await callback.answer('Некорректный выбор', show_alert=True)
        return
    details = udb.get_trainer_details(trainer_id)
    if not details:
        await callback.answer('Тренер не найден', show_alert=True)
        return
    await state.update_data(trainer_edit_id=trainer_id)
    await callback.message.answer(_format_trainer_details(details), reply_markup=_trainer_fields_keyboard(trainer_id))
    await state.set_state(TrainerDataStates.choose_field)
    await callback.answer()


@admin_router.callback_query(F.data=='tr_back')
async def trainer_back_to_list(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    trainers = udb.list_trainers()
    if not trainers:
        await callback.message.answer('Список тренеров пуст.', reply_markup=trener_kb)
        await state.clear()
        await callback.answer()
        return
    
    # Получаем сохраненную страницу или используем 0
    data = await state.get_data()
    page = data.get('trainer_list_page', 0)
    
    # Удаляем предыдущее сообщение и отправляем список выбора
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer('Выберите тренера для редактирования:', reply_markup=_trainer_select_keyboard(trainers, page=page))
    await state.set_state(TrainerDataStates.select_trainer)
    await callback.answer()
    await callback.answer()


def _employment_edit_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text='Самозанятый')],
            [types.KeyboardButton(text='ИП')],
            [types.KeyboardButton(text='Отмена')]
        ],
        resize_keyboard=True
    )


@admin_router.callback_query(F.data.startswith('tr_birthday_toggle:'))
async def trainer_birthday_toggle(callback: CallbackQuery, state: FSMContext):
    """Переключение отключения поздравлений с днем рождения"""
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    
    try:
        trainer_id = int(callback.data.split(':')[1])
    except (ValueError, IndexError):
        await callback.answer('Ошибка', show_alert=True)
        return
    
    details = udb.get_trainer_details(trainer_id)
    if not details:
        await callback.answer('Тренер не найден', show_alert=True)
        return
    
    current_state = details.get('birthday_notifications_disabled', False)
    new_state = not current_state
    
    udb.set_birthday_notifications_disabled(trainer_id, new_state)
    
    # Обновляем данные и показываем обновленную клавиатуру
    details = udb.get_trainer_details(trainer_id)
    status_text = 'отключены' if new_state else 'включены'
    await callback.answer(f'Поздравления с ДР {status_text}')
    await callback.message.edit_text(
        _format_trainer_details(details),
        reply_markup=_trainer_fields_keyboard(trainer_id)
    )


@admin_router.callback_query(F.data.startswith('tr_field:'))
async def trainer_field_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in admins:
        await callback.answer('Нет прав', show_alert=True)
        return
    try:
        _, trainer_part, field_key = callback.data.split(':', maxsplit=2)
        trainer_id = int(trainer_part)
    except ValueError:
        await callback.answer('Некорректный выбор', show_alert=True)
        return
    await state.update_data(trainer_edit_id=trainer_id, trainer_edit_field=field_key)
    if field_key == 'employment_type':
        await callback.message.answer('Выберите статус занятости:', reply_markup=_employment_edit_keyboard())
    elif field_key in {'med_date', 'qual_date', 'birthday'}:
        target = 'Медкомиссии' if field_key == 'med_date' else ('повышения квалификации' if field_key == 'qual_date' else 'дня рождения')
        await callback.message.answer(f'Введите дату {target} в формате ДД.ММ.ГГГГ:', reply_markup=cancel_kb)
    elif field_key == 'email':
        await callback.message.answer('Введите email (например, user@example.com):', reply_markup=cancel_kb)
    elif field_key == 'nickname':
        await callback.message.answer('Введите новое ФИО (Фамилия Имя):', reply_markup=cancel_kb)
    elif field_key == 'phone':
        await callback.message.answer('Введите номер телефона:', reply_markup=cancel_kb)
    else:
        await callback.message.answer('Введите новое значение:', reply_markup=cancel_kb)
    await state.set_state(TrainerDataStates.input_value)
    await callback.answer()


async def _validate_and_apply_trainer_update(trainer_id: int, field_key: str, value: str) -> tuple[bool, str | None]:
    value = value.strip()
    details = udb.get_trainer_details(trainer_id)
    if not details:
        return False, 'Тренер не найден.'
    if field_key == 'nickname':
        if len(value.split()) < 2:
            return False, 'Укажите Фамилию и Имя.'
        old_name = details.get('nickname')
        udb.update_trainer_field(trainer_id, 'nickname', value)
        if old_name and old_name != value:
            udb.change_nickname_in_meet(value, old_name)
            if sheets_service and sheets_service.is_available():
                try:
                    await sheets_service.update_user_name(old_name, value)
                except Exception as e:
                    print(f'Error syncing name change: {e}')
    elif field_key == 'phone':
        if len(value) < 5:
            return False, 'Слишком короткий номер телефона.'
        udb.update_trainer_field(trainer_id, 'phone', value)
    elif field_key == 'email':
        if not EMAIL_REGEX.fullmatch(value):
            return False, 'Некорректный формат email.'
        udb.update_trainer_field(trainer_id, 'email', value)
    elif field_key == 'employment_type':
        if value not in {'Самозанятый', 'ИП'}:
            return False, 'Выберите один из предложенных вариантов.'
        code = 'СЗ' if value == 'Самозанятый' else 'ИП'
        udb.update_trainer_field(trainer_id, 'employment_type', code)
    elif field_key == 'birthday':
        try:
            day, month, year = map(int, value.split('.'))
            datetime(year, month, day)
        except Exception:
            return False, 'Некорректная дата. Формат: ДД.ММ.ГГГГ.'
        udb.set_birthday_by_id(trainer_id, value)
    elif field_key in {'med_date', 'qual_date'}:
        try:
            day, month, year = map(int, value.split('.'))
            datetime(year, month, day)
        except Exception:
            return False, 'Некорректная дата. Формат: ДД.ММ.ГГГГ.'
        if field_key == 'med_date':
            udb.set_med_date(trainer_id, value)
            if sheets_service and sheets_service.is_available():
                try:
                    await sheets_service.sync_trainer_medical(details.get('nickname'), value)
                except Exception as e:
                    print(f'Error syncing medical date: {e}')
        else:
            udb.set_qual_date(trainer_id, value)
            if sheets_service and sheets_service.is_available():
                try:
                    await sheets_service.sync_trainer_qualification(details.get('nickname'), value)
                except Exception as e:
                    print(f'Error syncing qualification date: {e}')
        return True, None
    else:
        return False, 'Поле недоступно для редактирования.'

    if field_key in {'nickname', 'phone', 'email', 'employment_type', 'birthday'}:
        await _sync_trainer_registration(trainer_id)
    return True, None


@admin_router.message(TrainerDataStates.input_value)
async def trainer_field_input(message: types.Message, state: FSMContext):
    if message.text == 'Отмена':
        await state.set_state(TrainerDataStates.choose_field)
        await message.answer('Действие отменено.', reply_markup=trener_kb)
        return
    data = await state.get_data()
    trainer_id = data.get('trainer_edit_id')
    field_key = data.get('trainer_edit_field')
    if not trainer_id or not field_key:
        await state.clear()
        await message.answer('Состояние утеряно, начните заново.', reply_markup=trener_kb)
        return
    ok, error = await _validate_and_apply_trainer_update(trainer_id, field_key, message.text)
    if not ok:
        await message.answer(error or 'Не удалось сохранить. Попробуйте снова.')
        return
    await message.answer('Изменения сохранены.', reply_markup=ReplyKeyboardRemove())
    details = udb.get_trainer_details(trainer_id)
    if details:
        await message.answer(_format_trainer_details(details), reply_markup=_trainer_fields_keyboard(trainer_id))
    await state.set_state(TrainerDataStates.choose_field)




@admin_router.callback_query(F.data=='year')
async def calendaric_year(callback: CallbackQuery):
    current_year = str(datetime.now().year)
    await callback.answer(f'Текущий год-{current_year}')

@admin_router.callback_query(F.data=='weekday')
@admin_router.callback_query(F.data=='month')
async def calendaric_month(callback: CallbackQuery, state: FSMContext):
    meet=await state.get_data()
    month = meet['month']
    await callback.answer(f'Текущий месяц-{month}')


@admin_router.message(F.text=='Создать встречу')
async def make_meet(message: types.Message, state: FSMContext):
    await message.answer('Выберите месяц', reply_markup=await calendar_month())
    await state.set_state(AddMeet.month)

@admin_router.callback_query(AddMeet.month)
async def calendaric_month(callback: CallbackQuery, state: FSMContext):
    month=callback.data
    await state.update_data(month=month)
    await callback.message.edit_text('Выберите дату', reply_markup=await calendar_day(month))
    await state.set_state(AddMeet.day)

@admin_router.callback_query(AddMeet.day)
async def calendaric_day(callback: CallbackQuery, state: FSMContext):
    day=callback.data
    if day=='назад':
        await callback.message.edit_text('Выберите месяц', reply_markup=await calendar_month())
        await state.set_state(AddMeet.month)
    else:
        await state.update_data(day=day)
        meet = await state.get_data()
        month = meet['month']
        day = meet['day']
        if int(day) < 10:
            day = '0' + day
        months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
        month = str(months.index(month) + 1)
        if int(month) < 10:
            month = '0' + month
        date = day + '.' + month
        await callback.message.edit_text('Выберите время', reply_markup=await calendar_time(date))
        await state.set_state(AddMeet.time)

time_list=set()

@admin_router.callback_query(AddMeet.time)
async def select_name(callback: CallbackQuery, state: FSMContext):
        global time_list
        times=callback.data
        meet = await state.get_data()
        day = meet['day']
        month = meet['month']
        date = day + '.' + month
        if times == 'назад':
            time_list = set()
            await callback.message.delete()
            await callback.message.answer('Выберите дату', reply_markup=await calendar_day(month))
            await state.set_state(AddMeet.day)
        elif callback.data == 'создать встречи':
            if len(time_list)==0:
                await callback.answer('Вы не выбрали время!')
                await callback.message.edit_text('Выберите время', reply_markup=await calendar_time(date, dobavlen=time_list))
                await state.set_state(AddMeet.time)
            else:
                for i in time_list:
                    day = meet['day']
                    month = meet['month']
                    status1 = 'Можно записаться'
                    status2 = 'None'
                    if len(db.count_meet()) == 0:
                        name = 1
                    else:
                        name = max(db.count_meet()) + 1
                    if int(day) < 10:
                        day = '0' + day
                    months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                              'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
                    month = str(months.index(month) + 1)
                    if int(month) < 10:
                        month = '0' + month
                    date = day + '.' + month
                    db.add_name_meet(name)
                    db.add_date_meet(name, date)
                    db.add_time_meet(name, i)
                    db.add_zapis_meet(status1, name)
                    db.add_client_meet(status2, name)
                    await callback.message.answer(f'Отлично, вы создали встречу на {date} на {i}', reply_markup=admin_kb)
            await state.clear()
            time_list=set()
        else:
            if callback.data in time_list:
                time_list.discard(callback.data)
                await callback.message.edit_text('Выберите время', reply_markup=await calendar_time(date, dobavlen=time_list))
                await state.set_state(AddMeet.time)
            else:
                time_list.add(callback.data)
                await callback.message.edit_text('Выберите время', reply_markup=await calendar_time(date, dobavlen=time_list))
                await state.set_state(AddMeet.time)


@admin_router.message(F.text=='Встречи на сегодня')
async def raspisanie_na_segodnya(message: types.Message, bot: Bot):
    meet = db.name_meet()
    message_to_answer = ''
    if len(meet) == 0:
        await message.answer('Встреч пока нет!')
    else:
        # Получаем текущую дату
        today = date.today()
        current_month = today.month
        current_day = today.day
        
        # Создаем список для сортировки
        meet_list = []
        for names in range(0, len(meet) - 2, 4):
            client = meet[names]
            name = meet[names + 1]
            times = meet[names + 2]
            dates = meet[names + 3]
            
            # Пропускаем встречи без тренера
            if client == 'None':
                continue
                
            # Разбиваем дату на компоненты (день-месяц)
            day, month = dates.split('.')
            meet_day = int(day)
            meet_month = int(month)
            
            # Создаем даты для сравнения
            current_date = date(2024, current_month, current_day)
            meet_date = date(2024, meet_month, meet_day)
            
            # Если встреча уже прошла в этом году, берем следующий год
            if meet_date < current_date:
                meet_date = date(2025, meet_month, meet_day)
            
            # Вычисляем разницу в днях
            diff_days = (meet_date - current_date).days
            
            if diff_days == 0:
                week_day = meet_date.weekday()
                weekdays_dict = {0: 'понедельник', 1: 'вторник',
                             2: 'среда', 3: 'четверг',
                             4: 'пятница', 5: 'суббота',
                             6: 'воскресенье'}
                # Добавляем информацию о встрече в список
                meet_list.append({
                    'client': client,
                    'name': name,
                    'time': times,
                    'date': dates,
                    'week_day': weekdays_dict[week_day],
                    'sort_time': datetime.strptime(times, '%H:%M').time()
                })
        
        # Сортируем по времени
        meet_list.sort(key=lambda x: x['sort_time'])
        
        # Формируем сообщение
        for meet in meet_list:
            message_to_answer += f'Встреча №{meet["name"]}\nДата: {meet["date"]}\nДень недели: {meet["week_day"]}\nВремя: {meet["time"]}\nТренер: {meet["client"]}\n\n'
        
        if message_to_answer == '':
            await message.answer('На сегодня никто не записан(')
        else:
            await message.answer(message_to_answer, reply_markup=admin_kb)





@admin_router.message(F.text=='Все встречи')
async def raspisanie(message: types.Message):
    meet = db.name_meet()
    message_to_answer = ''
    if len(meet) == 0:
        await message.answer('Встреч пока нет!')
    else:
        # Создаем список для сортировки
        meet_list = []
        for names in range(0, len(meet) - 2, 4):
            client = meet[names]
            name = meet[names + 1]
            time = meet[names + 2]
            date = meet[names + 3]
            list_date = date.split('.')
            week_day = datetime(int(datetime.now().year), int(list_date[1]), int(list_date[0])).weekday()
            weekdays_dict = {0: 'понедельник', 1: 'вторник',
                             2: 'среда', 3: 'четверг',
                             4: 'пятница', 5: 'суббота',
                             6: 'воскресенье'}
            
            # Добавляем информацию о встрече в список без гиперссылок
            meet_list.append({
                'client': client,
                'name': name,
                'time': time,
                'date': date,
                'week_day': weekdays_dict[week_day],
                'sort_date': datetime(int(datetime.now().year), int(list_date[1]), int(list_date[0])),
                'sort_time': datetime.strptime(time, '%H:%M').time()
            })
        
        # Сортируем по дате и времени
        meet_list.sort(key=lambda x: (x['sort_date'], x['sort_time']))
        
        # Формируем сообщение
        for meet in meet_list:
            message_to_answer += f'Встреча №{meet["name"]}\nДата: {meet["date"]}\nДень недели: {meet["week_day"]}\nВремя: {meet["time"]}\nТренер: {meet["client"]}\n'
            message_to_answer += '\n'
        await message.answer(message_to_answer, reply_markup=admin_kb)


@admin_router.message(F.text=='Расписание встреч')
async def all_meet(message: types.Message):
    meet = db.name_meet()
    message_to_answer = ''
    if len(meet) == 0:
        await message.answer('Встреч пока нет!')
    else:
        # Создаем список для сортировки
        meet_list = []
        for names in range(0, len(meet) - 2, 4):
            client = meet[names]
            name = meet[names + 1]
            time = meet[names + 2]
            date = meet[names + 3]
            list_date = date.split('.')
            week_day = datetime(int(datetime.now().year), int(list_date[1]), int(list_date[0])).weekday()
            weekdays_dict = {0: 'понедельник', 1: 'вторник',
                             2: 'среда', 3: 'четверг',
                             4: 'пятница', 5: 'суббота',
                             6: 'воскресенье'}
            if client != 'None':
                # Добавляем информацию о встрече в список
                meet_list.append({
                    'client': client,
                    'name': name,
                    'time': time,
                    'date': date,
                    'week_day': weekdays_dict[week_day],
                    'sort_date': datetime(int(datetime.now().year), int(list_date[1]), int(list_date[0])),
                    'sort_time': datetime.strptime(time, '%H:%M').time()
                })
        
        # Сортируем по дате и времени
        meet_list.sort(key=lambda x: (x['sort_date'], x['sort_time']))
        
        # Формируем сообщение
        for meet in meet_list:
            message_to_answer += f'Встреча №{meet["name"]}\nДата: {meet["date"]}\nДень недели: {meet["week_day"]}\nВремя: {meet["time"]}\nТренер: {meet["client"]}\n'
            message_to_answer += '\n'
        
        if message_to_answer == '':
            await message.answer('Никто не записан на встречи(', reply_markup=admin_kb)
        else:
            await message.answer(message_to_answer, reply_markup=admin_kb, parse_mode='HTML')


@admin_router.message(F.text.lower()=='назад')
async def back(message: types.Message, state: FSMContext):
    await message.answer('Перевожу вас в главное меню!', reply_markup=admin_kb)
    await state.clear()

@admin_router.message(F.text=='Отменить/перенести')
async def much_meet(message: types.Message, state: FSMContext):
    meet=db.name_meet()
    message_to_answer=''
    number=1
    if len(meet)==0:
        await message.answer('Встреч пока нет!')
    else:
        for names in range(0,len(meet)-2,4):
            client = meet[names]
            name = meet[names+1]
            time = meet[names+2]
            date = meet[names+3]
            message_to_answer+=f'Встреча №{name}\nДата: {date}\nВремя: {time}\nТренер: {client}\n'
            message_to_answer+='\n'
            number+=1
        await message.answer('Выберите номер встречи')
        await message.answer(message_to_answer, reply_markup= ReplyKeyboardRemove())
        await state.set_state(ChangeMeet.vvod)

@admin_router.message(ChangeMeet.vvod, F.text)
async def change_meet(message: types.Message, state: FSMContext):
    await state.clear()
    global chose
    chose=message.text
    await message.answer('Что вы хотите с ней сделать?', reply_markup=change_kb)

@admin_router.message(F.text=='Удалить встречу')
async def delete_meet(message: types.Message, bot:Bot):
        if db.meet_exists(chose):
            if db.select_delete_client(chose)=='None':
                db.delete_meet(chose)
                await message.answer(f'Встреча {chose} успешно удалена!', reply_markup=admin_kb)
            else:
                nick_in_zapis=db.select_delete_client(chose)
                user_id=db.get_id(nick_in_zapis)
                if user_id is not None:
                    await bot.send_message(user_id, 'Встреча на которую вы записывались была удалена, пожалуйста запишитесь на другую!')
                db.delete_meet(chose)
                await message.answer(f'Встреча {chose} успешно удалена!', reply_markup=admin_kb)
        else:
            await message.answer(f'Встречи на {chose} нет!')


class Confirm(StatesGroup):
    da_net= State()


@admin_router.message(F.text=='Удалить все встречи')
async def delete_meet(message: types.Message, state: FSMContext):
    await message.answer('Вы уверены что хотите удалить все встречи?', reply_markup=confirm_kb)
    await state.set_state(Confirm.da_net)


@admin_router.message(F.text, Confirm.da_net)
async def delete_meet(message: types.Message, state: FSMContext):
    if message.text=='Да ✅':
        meet = db.name_meet()
        for names in range(0,len(meet)-2,4):
            client = meet[names]
            name = meet[names+1]
            if db.select_delete_client(name) == 'None':
                db.delete_meet(name)
                await message.answer(f'Встреча {name} успешно удалена!', reply_markup=admin_kb)
            else:
                nick_in_zapis = db.select_delete_client(name)
                id = db.get_id(nick_in_zapis)
                db.delete_meet(name)
                await bot.send_message(id,
                                       'Встреча на которую вы записывались была удалена, пожалуйста запишитесь на дргую!')
                await message.answer(f'Встреча {name} успешно удалена!', reply_markup=admin_kb)


    elif message.text=='Нет ❌':
        await message.answer('Хорошо, не удаляю!', reply_markup=admin_kb)
        await state.clear()
    else:
        await message.answer('Не понял(')
        await state.set_state(Confirm.da_net)



@admin_router.message(F.text=='Изменить время')
async def change_time(message: types.Message, state: FSMContext):
    if db.meet_exists(chose):
        await state.set_state(ChangeMeet.time)
        await message.answer('Введите новое время', reply_markup=await calendar_time(str(date.today())[5:].replace('-', '.')))
    else:
        await message.answer('Такой встречи нет')

@admin_router.message(F.text=='Изменить дату')
async def change_date(message: types.Message, state: FSMContext):
    if db.meet_exists(chose):
        await state.set_state(ChangeMeet.month)
        await message.answer('Введите новую дату', reply_markup= await calendar_month())
    else:
        await message.answer('Такой встречи нет')


@admin_router.callback_query(ChangeMeet.time)
async def change_time1(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(time=callback.data)
    await callback.message.delete()
    meet = await state.get_data()
    time = meet['time']
    db.add_time_meet(chose, time)
    await state.clear()
    await callback.message.answer(f'Время успешно изменено на {time}', reply_markup=admin_kb)
    nick_in_zapis = db.select_delete_client(chose)
    if nick_in_zapis != 'None':
        user_id = db.get_id(nick_in_zapis)
        if user_id is not None:
            await bot.send_message(user_id, f'Время встречи, на которую вы записывались изменилось на {time}')


@admin_router.callback_query(ChangeMeet.month)
async def change_date1(callback: CallbackQuery, state: FSMContext):
    await state.update_data(month=callback.data)
    await callback.message.edit_text('Выберите новую дату', reply_markup= await calendar_day(callback.data))
    await state.set_state(ChangeMeet.day)


@admin_router.callback_query(ChangeMeet.day)
async def change_date1(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(day=callback.data)
    await callback.message.delete()
    meet = await state.get_data()
    month = meet['month']
    day = meet['day']
    if int(day) < 10:
        day = '0' + day
    months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
              'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
    month = str(months.index(month) + 1)
    if int(month) < 10:
        month = '0' + month
    date = day + '.' + month
    db.add_date_meet(chose, date)
    await state.clear()
    await callback.message.answer(f'Дата успешно изменена на {date}', reply_markup=admin_kb)
    nick_in_zapis = db.select_delete_client(chose)
    if nick_in_zapis != 'None':
        id = db.get_id(nick_in_zapis)
        await bot.send_message(id, f'Время встречи, на которую вы записывались изменилось на {date}')


@admin_router.message(F.text=='отпр увед')
async def change_name1(bot: Bot):
    zapis='Мест нет'
    list_clients=db.select_client_meet(zapis)
    date_today=str(date.today())[5:].split('-')
    print(date_today, type(date_today), date_today[0], int(date_today[1]))
    for client in list_clients:
        dict_client_data=db.select_date_client(client)
        dates=dict_client_data[client]
        date_time=datetime(2024, int(dates.split('.')[1]), int(dates.split('.')[0]))
        date_toda=datetime(2024, int(date_today[1]), int(date_today[0]))
        
        if (date_time-date_toda).days==1:
            time_meet=db.select_time_client(client)
            id=db.get_id(client)

            await bot.send_message(id, f'У тебя завтра встреча в {time_meet}, не забудь!')


def _calculate_upcoming_birthday(birthday: str, today: date) -> tuple[date | None, int | None]:
    if not birthday:
        return None, None
    try:
        day, month, year = map(int, birthday.split('.'))
    except ValueError:
        return None, None
    upcoming = date(year=today.year, month=month, day=day)
    if upcoming < today:
        upcoming = date(year=today.year + 1, month=month, day=day)
    days_until = (upcoming - today).days
    return upcoming, days_until


async def notify_birthdays(bot: Bot):
    list_birth = db.check_dr()
    if not list_birth:
        logger.info('Список дней рождений пуст')
        return

    today = date.today()
    logger.info(f'Проверка дней рождений на {today}. Всего записей в БД: {len(list_birth)}')
    
    supers_notifications: dict[int, list[str]] = {2: [], 1: [], 0: []}
    work_congratulations: list[tuple[str, str, str]] = []
    
    # Обрабатываем уникальные даты рождения, чтобы не дублировать обработку
    unique_birthdays = list(set(list_birth))
    logger.debug(f'Уникальных дат рождения: {len(unique_birthdays)}')
    
    for birthday in unique_birthdays:
        if not isinstance(birthday, str):
            logger.debug(f'Пропущена запись дня рождения (не строка): {birthday}')
            continue
        upcoming, days_until = _calculate_upcoming_birthday(birthday, today)
        if upcoming is None or days_until is None:
            logger.debug(f'Не удалось вычислить день рождения для: {birthday}')
            continue
        
        # Получаем ВСЕХ людей с этой датой рождения
        with db.connection:
            result = db.cursor.execute("SELECT `nickname` FROM `users` WHERE `birthday`=?", (birthday,))
            nicknames = [str(row[0]) for row in result if row[0]]
        
        if not nicknames:
            logger.debug(f'Не найдены никнеймы для дня рождения: {birthday}')
            continue

        logger.debug(f'Дата рождения {birthday}: найдено {len(nicknames)} человек(а)')

        # Обрабатываем каждого человека с этой датой рождения
        for nickname in nicknames:
            logger.debug(f'День рождения: {nickname}, дата: {upcoming}, дней до: {days_until}')

            # Проверяем, является ли это тренером и отключены ли для него поздравления
            trainer_id = udb.get_trainer_id_by_name(nickname)
            if trainer_id and udb.is_birthday_notifications_disabled(trainer_id):
                logger.debug(f'Поздравления с ДР отключены для тренера {nickname} (ID: {trainer_id}), пропускаем')
                continue

            if days_until in supers_notifications:
                supers_notifications[days_until].append(f"• {nickname} — {upcoming.strftime('%d.%m')}")
            if days_until == 0:
                username = udb.get_username_by_nickname(nickname)
                mention = f" @{username}" if username else ''
                first_name = nickname.split(maxsplit=1)[1] if len(nickname.split()) > 1 else nickname
                work_congratulations.append((nickname, mention, first_name))
                logger.info(f'Найдено поздравление на сегодня: {nickname} (username: {username or "нет"})')

    logger.info(f'Найдено поздравлений на сегодня: {len(work_congratulations)}')

    headers = {
        2: "🎂 Напоминание: через 2 дня день рождения у:",
        1: "🎂 Напоминание: завтра день рождения у:",
        0: "🎉 Сегодня день рождения празднуют:"
    }

    for offset, lines in supers_notifications.items():
        if not lines:
            continue
        message_text = '\n'.join([headers[offset]] + lines)
        try:
            await bot.send_message(SUPERS_GROUP_ID, message_text, message_thread_id=1)
            logger.info(f'Отправлено уведомление о днях рождениях (offset={offset}, количество={len(lines)})')
        except Exception as e:
            logger.error(f'Ошибка отправки уведомления о днях рождениях (offset={offset}): {e}')

    sent_count = 0
    failed_count = 0
    for nickname, mention, first_name in work_congratulations:
        text = (
            f"Коллеги, сегодня свой день рождения празднует {nickname}{mention}!\n"
            f"{first_name}, с днем рождения 🎊"
        )
        try:
            await bot.send_message(WORK_BDAY_GROUP_ID, text)
            sent_count += 1
            logger.info(f'Поздравление отправлено: {nickname}')
        except Exception as e:
            failed_count += 1
            logger.error(f'Ошибка отправки поздравления для {nickname} в "Кроме работы": {e}')
    
    logger.info(f'Итого поздравлений: отправлено {sent_count}, ошибок {failed_count} из {len(work_congratulations)}')


@admin_router.message(F.text.lower() == 'чек др')
async def manual_birthday_check(message: types.Message, bot: Bot):
    await notify_birthdays(bot)
    await message.answer('Проверил предстоящие дни рождения.', reply_markup=admin_kb)


@admin_router.message(F.text == 'чек др сегодня')
async def manual_birthday_today(message: types.Message, bot: Bot):
    await notify_birthdays(bot)
    await message.answer('Напоминания по дням рождениям отправлены.', reply_markup=admin_kb)


@admin_router.message(F.text == 'уведомление илье')
async def yved_ikya_o_vstreche(bot: Bot):
    meet = db.name_meet()
    message_to_answer = ''
    # Получаем текущую дату
    today = date.today()
    current_month = today.month
    current_day = today.day
    
    for names in range(0, len(meet) - 2, 4):
        client = meet[names]
        name = meet[names + 1]
        times = meet[names + 2]
        dates = meet[names + 3]
        
        # Разбиваем дату на компоненты (день-месяц)
        day, month = dates.split('.')
        meet_day = int(day)
        meet_month = int(month)
        
        # Создаем даты для сравнения
        current_date = date(2024, current_month, current_day)
        meet_date = date(2024, meet_month, meet_day)
        
        # Если встреча уже прошла в этом году, берем следующий год
        if meet_date < current_date:
            meet_date = date(2025, meet_month, meet_day)
        
        # Вычисляем разницу в днях
        diff_days = (meet_date - current_date).days
        
        # Если встреча сегодня и есть клиент
        if diff_days == 0 and client != 'None':
            week_day = meet_date.weekday()
            weekdays_dict = {0: 'понедельник', 1: 'вторник',
                         2: 'среда', 3: 'четверг',
                         4: 'пятница', 5: 'суббота',
                         6: 'воскресенье'}
            message_to_answer += f'Встреча №{name}\nДата: {dates}\nДень недели: {weekdays_dict[week_day]}\nВремя: {times}\nТренер: {client}\n'
            message_to_answer += '\n'


    
    if message_to_answer != '':
        await bot.send_message(676770835, message_to_answer)
        await bot.send_message(676770835, 'Это все встречи, запланированные на сегодня')


@admin_router.message(NotificationStates.create_group_thread)
async def notifications_create_group_thread(message: types.Message, state: FSMContext):
    text = (message.text or '').strip().lower()
    data = await state.get_data()
    prompts = data.get('thread_prompt_list', [])
    index = data.get('thread_prompt_index', 0)
    if not prompts or index >= len(prompts):
        await _finalize_new_notification(message, state)
        return
    if text in {'отмена'}:
        await state.update_data(new_notification=None, thread_prompt_list=None, thread_prompt_index=0)
        await _send_notifications_menu(message, state)
        return
    thread_id = None
    if text in {'0', 'нет', 'без', 'пропустить'}:
        thread_id = None
    else:
        if not text.isdigit():
            await message.answer('Введите числовой ID темы или 0, если тема не нужна:')
            return
        thread_id = int(text)
    prompts[index]['thread_id'] = None if thread_id in (None, 0) else thread_id
    await state.update_data(thread_prompt_list=prompts, thread_prompt_index=index + 1)
    await _ask_next_thread(message, state, create_flow=True)


@admin_router.message(NotificationStates.edit_group_thread)
async def notifications_edit_group_thread(message: types.Message, state: FSMContext):
    text = (message.text or '').strip().lower()
    data = await state.get_data()
    prompts = data.get('thread_prompt_list', [])
    index = data.get('thread_prompt_index', 0)
    if not prompts or index >= len(prompts):
        await _return_to_edit_menu(message, state)
        return
    if text in {'назад', 'отмена'}:
        await state.update_data(thread_prompt_list=None, thread_prompt_index=0)
        await _return_to_edit_menu(message, state)
        return
    thread_id = None
    if text in {'0', 'нет', 'без', 'пропустить'}:
        thread_id = None
    else:
        if not text.isdigit():
            await message.answer('Введите числовой ID темы или 0, если тема не нужна:')
            return
        thread_id = int(text)
    prompts[index]['thread_id'] = None if thread_id in (None, 0) else thread_id
    await state.update_data(thread_prompt_list=prompts, thread_prompt_index=index + 1)
    await _ask_next_thread(message, state, create_flow=False)


def _needs_thread(group_id: int) -> bool:
    return group_id in THREADED_GROUPS


# --- Функции для работы с темами ---

def _parse_message_link(link: str) -> tuple[int | None, int | None]:
    """
    Парсит ссылку на сообщение Telegram и извлекает chat_id и message_id.
    
    Поддерживаемые форматы:
    - https://t.me/c/chat_id/message_id
    - https://t.me/username/message_id
    - https://t.me/c/chat_id/message_id?thread=thread_id
    
    Возвращает (chat_id, message_id) или (None, None) при ошибке.
    """
    if not link or not isinstance(link, str):
        return None, None
    
    link = link.strip()
    
    # Проверяем формат ссылки
    if not link.startswith('https://t.me/'):
        return None, None
    
    # Убираем параметры запроса
    if '?' in link:
        link = link.split('?')[0]
    
    parts = link.replace('https://t.me/', '').split('/')
    
    if len(parts) < 2:
        return None, None
    
    try:
        # Формат: c/chat_id/message_id
        if parts[0] == 'c' and len(parts) >= 3:
            chat_id = int(parts[1])
            message_id = int(parts[2])
            # Для супергрупп нужно добавить префикс -100
            if chat_id > 0:
                chat_id = int(f'-100{chat_id}')
            return chat_id, message_id
        
        # Формат: username/message_id
        # В этом случае нужно получить chat_id через API, но для начала вернем None
        # и попросим пользователя использовать формат с c/
        if len(parts) == 2:
            # Пытаемся извлечь message_id
            try:
                message_id = int(parts[1])
                # chat_id нужно будет получить через API
                return None, message_id
            except ValueError:
                return None, None
    except (ValueError, IndexError):
        return None, None
    
    return None, None






# --- Обработчики для уведомлений с текстами по дням недели ---

WEEKDAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
WEEKDAY_STATES = [
    NotificationStates.create_weekday_monday,
    NotificationStates.create_weekday_tuesday,
    NotificationStates.create_weekday_wednesday,
    NotificationStates.create_weekday_thursday,
    NotificationStates.create_weekday_friday,
    NotificationStates.create_weekday_saturday,
    NotificationStates.create_weekday_sunday,
]


@admin_router.message(NotificationStates.create_weekday_base_text)
async def notifications_create_weekday_base_text(message: types.Message, state: FSMContext):
    """Обработка ввода основного текста для уведомления с текстами по дням недели."""
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.update_data(new_notification=None, weekday_messages=None)
        await _send_notifications_menu(message, state, 'Создание уведомления отменено.')
        return
    if not text:
        await message.answer('Текст не может быть пустым. Введите основной текст уведомления:')
        return
    
    data = await state.get_data()
    new_notif = data.get('new_notification', {})
    new_notif['message'] = text
    await state.update_data(new_notification=new_notif)
    
    # Переходим к вводу текста для первого дня недели
    await state.update_data(weekday_current_day=0)
    await message.answer(
        f'Основной текст сохранен.\n\n'
        f'Теперь введите дополнительный текст для {WEEKDAY_NAMES[0]}.\n'
        f'Если дополнительный текст не нужен для этого дня, напишите "пропустить" или "нет".'
    )
    await state.set_state(NotificationStates.create_weekday_monday)


async def _process_weekday_text_input(message: types.Message, state: FSMContext, day_index: int):
    """Обработка ввода текста для конкретного дня недели."""
    text = (message.text or '').strip()
    if text.lower() in {'отмена', 'назад'}:
        await state.update_data(new_notification=None, weekday_messages=None)
        await _send_notifications_menu(message, state, 'Создание уведомления отменено.')
        return
    
    data = await state.get_data()
    weekday_messages = data.get('weekday_messages', {})
    
    # Если пользователь написал "пропустить" или "нет", не добавляем текст для этого дня
    if text.lower() not in {'пропустить', 'нет', 'skip', 'no', ''}:
        weekday_messages[WEEKDAY_NAMES[day_index]] = text
    
    await state.update_data(weekday_messages=weekday_messages)
    
    # Переходим к следующему дню или завершаем
    if day_index < 6:
        next_day_index = day_index + 1
        await state.update_data(weekday_current_day=next_day_index)
        await message.answer(
            f'Текст для {WEEKDAY_NAMES[day_index]} сохранен.\n\n'
            f'Введите дополнительный текст для {WEEKDAY_NAMES[next_day_index]}.\n'
            f'Если дополнительный текст не нужен, напишите "пропустить" или "нет".'
        )
        await state.set_state(WEEKDAY_STATES[next_day_index])
    else:
        # Все дни обработаны, переходим к выбору расписания
        await message.answer('Все тексты по дням недели сохранены. Теперь выберите расписание.')
        await _start_schedule_selection(message, state, mode='create')


@admin_router.message(NotificationStates.create_weekday_monday)
async def notifications_create_weekday_monday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 0)


@admin_router.message(NotificationStates.create_weekday_tuesday)
async def notifications_create_weekday_tuesday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 1)


@admin_router.message(NotificationStates.create_weekday_wednesday)
async def notifications_create_weekday_wednesday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 2)


@admin_router.message(NotificationStates.create_weekday_thursday)
async def notifications_create_weekday_thursday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 3)


@admin_router.message(NotificationStates.create_weekday_friday)
async def notifications_create_weekday_friday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 4)


@admin_router.message(NotificationStates.create_weekday_saturday)
async def notifications_create_weekday_saturday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 5)


@admin_router.message(NotificationStates.create_weekday_sunday)
async def notifications_create_weekday_sunday(message: types.Message, state: FSMContext):
    await _process_weekday_text_input(message, state, 6)



