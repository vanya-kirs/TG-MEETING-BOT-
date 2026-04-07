from aiogram import types, Router, F, Bot
from aiogram.enums import ChatType
from aiogram.filters import CommandStart

from buttons.buttons_user import start_kb, profile, back_kb, cancel_kb, yes_no_kb
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from database.client import Database
from database.meet import Database1
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from services.google_sheets import GoogleSheetsService
from datetime import datetime, timedelta
import os
import re
import logging
user_router = Router()
user_router.message.filter(F.chat.type == ChatType.PRIVATE)
user_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
db1=Database1('fio.db')
db=Database('fio.db')

logger = logging.getLogger(__name__)

# Initialize Google Sheets service if configured
sheets_id = os.getenv('GOOGLE_SHEETS_ID')
sheets_service = GoogleSheetsService(sheets_id) if sheets_id else None

SUPERS_GROUP_ID = -1003283404598
SUPERS_PAYMENTS_THREAD_ID = 81

# Группы для регистрации (4 группы)
REGISTRATION_GROUPS = {
    'Дежурства': -1003241813302,
    'Важное': -1003267461863,
    'Кроме работы': -1003280894419,
    'Общаяя': -1003258837348,
}

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def _is_valid_email(email: str) -> bool:
    if not email:
        return False
    return EMAIL_REGEX.fullmatch(email.strip()) is not None

ADMIN_IDS = [916539100, 676770835]


class SelectMeet(StatesGroup):
    # Шаги состояний
    select_meet = State()

class Registration(StatesGroup):
    password=State()
    name=State()
    birthday=State()
    phone=State()
    employment_type=State()
    email=State()
    username=State()
    rename=State()
    change_employment_type=State()
    change_email=State()

class PaymentState(StatesGroup):
    waiting_receipt = State()
    asking_if_payment = State()

class IdeaState(StatesGroup):
    waiting_text = State()

@user_router.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    db.create_table_client()
    db1.create_table_meet()
    user_id = message.from_user.id
    if db.user_exists(user_id):
        signup_status = db.get_signup(user_id)
        if signup_status != 'done':
            db.delete_user_by_user_id(user_id)
    if not db.user_exists(user_id):
        db.add_user(user_id)
        await message.answer('Для регистрации введите пароль:')
        await state.set_state(Registration.password)
    else:
        user_nickname = db.get_nickname(user_id)
        await state.clear()
        await message.answer(
            f'Здравствуйте, {user_nickname}!\nВы в главном меню!\n\nЯ бот секретарь , буду рад помочь вам записаться на встречу с супервайзером.',
            reply_markup=start_kb
        )

@user_router.message(Registration.password)
async def check_password(message: types.Message, state: FSMContext):
    if message.text.lower() == 'avik':
        await message.answer('Пароль верный! Представьтесь пожалуйста, напишите свою фамилию и имя 🤝')
        await state.set_state(Registration.name)
    else:
        await message.answer('Неверный пароль. Попробуйте снова.')


@user_router.message(Registration.name)
async def start(message: types.Message, state: FSMContext):
    nickname=message.text
    if len(nickname.split())==2:
        if nickname.split()[0].isalpha()==True and nickname.split()[1].isalpha()==True:
            await state.update_data(name=nickname)
            await message.answer('Супер! Очень хотелось бы узнать вашу дату рождения...подскажите пожалуйста\nФормат ввода:ДД.ММ.ГГГГ')
            await state.set_state(Registration.birthday)
        else:
            await message.answer('Вы должны использовать только символы киррилицы!')
            await state.set_state(Registration.name)
    else:
        await message.answer('Введите фамилию и имя!')


@user_router.message(Registration.birthday)
async def start(message: types.Message, state: FSMContext):
    birth=message.text
    if birth.count('.')==2:
        list_birth=birth.split('.')
        if int(list_birth[0])<=31 and int(list_birth[1])<=12 and len(list_birth[0])==2 and len(list_birth[1])==2 and len(list_birth[2])==4:
            await state.update_data(birthday=birth)
            Registrat = await state.get_data()
            name = Registrat['name']
            birthday=Registrat['birthday']
            db.set_nickname(message.from_user.id, name)
            db.set_birthday(message.from_user.id, birthday)
            # Запрос телефона через кнопку с request_contact
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text='Отправить телефон', request_contact=True)]],
                resize_keyboard=True
            )
            await message.answer('Поделитесь, пожалуйста, номером телефона кнопкой ниже', reply_markup=kb)
            await state.set_state(Registration.phone)
        else:
            await message.answer('Некорректная дата')
@user_router.message(Registration.phone, F.contact)
async def save_phone_contact(message: types.Message, state: FSMContext):
    contact = message.contact
    if contact and contact.phone_number:
        db.set_phone(message.from_user.id, contact.phone_number)
        await state.update_data(phone=contact.phone_number)
    # После телефона запрашиваем выбор самозанятый/ИП
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Самозанятый')],
            [KeyboardButton(text='ИП')]
        ],
        resize_keyboard=True
    )
    await message.answer('Укажите ваш статус занятости:', reply_markup=kb)
    await state.set_state(Registration.employment_type)


@user_router.message(Registration.phone)
async def phone_require_contact(message: types.Message, state: FSMContext):
    # Разрешаем только контакт. Иначе — просим нажать кнопку повторно
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Отправить телефон', request_contact=True)]],
        resize_keyboard=True
    )
    await message.answer('Чтобы продолжить, нажмите кнопку "Отправить телефон" ниже', reply_markup=kb)

@user_router.message(Registration.employment_type)
async def save_employment_type(message: types.Message, state: FSMContext):
    emp_type_text = message.text
    if emp_type_text not in ['Самозанятый', 'ИП']:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Самозанятый')],
                [KeyboardButton(text='ИП')]
            ],
            resize_keyboard=True
        )
        await message.answer('Пожалуйста, выберите один из вариантов ниже', reply_markup=kb)
        return
    
    # Сохраняем как СЗ или ИП
    emp_type = 'СЗ' if emp_type_text == 'Самозанятый' else 'ИП'
    await state.update_data(employment_type=emp_type)
    db.set_employment_type(message.from_user.id, emp_type)
    
    # Переходим к получению username
    await proceed_username_step(message, state)


async def _prompt_email_input(message: types.Message, state: FSMContext):
    await message.answer('Введите адрес электронной почты (например, user@example.com):', reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.email)


async def _complete_registration(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    full_name = data.get('name') or db.get_nickname(user_id)
    phone = db.get_phone(user_id) or data.get('phone', '')
    birthday = data.get('birthday', '')
    employment_type = data.get('employment_type', '')
    email = data.get('email', '')

    db.set_signup(user_id, 'done')
    if email:
        db.set_email(user_id, email)

    if sheets_service and sheets_service.is_available() and full_name:
        try:
            await sheets_service.sync_user_registration({
                'full_name': full_name,
                'phone': phone,
                'birthday': birthday,
                'employment_type': employment_type,
                'email': email,
            })
            await sheets_service.sync_user_name_to_all_sheets(full_name)
            await sheets_service.update_user_email(full_name, email)
        except Exception as e:
            print(f"Error syncing to Sheets during completion: {e}")

    await message.answer(
        f"Регистрация завершена. Ваш ник: @{message.from_user.username or data.get('username', 'unknown')}",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        'Теперь вы можете записаться на встречу, выбрав соответствующую клавишу в меню⬇️⬇️⬇️',
        reply_markup=start_kb
    )
    
    # Создаем одноразовые ссылки для всех групп
    await message.answer('Присоединяйтесь к нашим группам:')
    bot = message.bot
    
    for group_name, group_id in REGISTRATION_GROUPS.items():
        try:
            # Создаем одноразовую ссылку, действующую 12 часов
            expire_date = datetime.utcnow() + timedelta(hours=12)
            invite_link = await bot.create_chat_invite_link(
                chat_id=group_id,
                name=f"Регистрация {group_name}",
                expire_date=expire_date,
                member_limit=1  # Одноразовая ссылка
            )
            await message.answer(f'🔹 {group_name}:\n{invite_link.invite_link}')
            logger.info(f'Создана одноразовая ссылка для группы {group_name} (ID: {group_id})')
        except Exception as e:
            logger.error(f'Ошибка создания ссылки для группы {group_name} (ID: {group_id}): {e}', exc_info=True)
            await message.answer(f'❌ Не удалось создать ссылку для группы "{group_name}". Обратитесь к администратору.')
    
    await state.clear()

async def proceed_username_step(message: types.Message, state: FSMContext):
    auto_username = message.from_user.username
    if auto_username:
        db.set_username(message.from_user.id, auto_username)
        await state.update_data(username=auto_username)
        await _prompt_email_input(message, state)
        return
    await message.answer('Укажите ваш Telegram username: пришлите @username или ссылку t.me/username', reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.username)


@user_router.message(Registration.username)
async def reg_username(message: types.Message, state: FSMContext):
    def _norm(text: str) -> str | None:
        t = text.strip()
        if t.startswith('@'):
            t = t[1:]
        for pref in ('https://t.me/','http://t.me/','t.me/'):
            if t.startswith(pref):
                t = t[len(pref):]
        t = t.split('?')[0].strip('/')
        import re
        return t if re.fullmatch(r"[A-Za-z0-9_]{5,32}", t or '') else None

    uname = _norm(message.text)
    if not uname:
        await message.answer('Некорректный username. Пришлите @username или ссылку t.me/username')
        return
    db.set_username(message.from_user.id, uname)
    await state.update_data(username=uname)
    await _prompt_email_input(message, state)


@user_router.message(Registration.email)
async def capture_email(message: types.Message, state: FSMContext):
    email = (message.text or '').strip()
    if not _is_valid_email(email):
        await message.answer('Некорректный формат. Введите email вида user@example.com:')
        return
    db.set_email(message.from_user.id, email)
    await state.update_data(email=email)
    await _complete_registration(message, state)

@user_router.message(F.text=='Мои записи')
async def profil(message: types.Message):
    client=db1.client_exists()
    nickname=db.get_nickname(message.from_user.id)
    if nickname in client:
        meet= db1.meet_by_client(nickname)
        time = db.time_zapis(meet)
        date = db.date_zapis(meet)
        await message.answer(f'Ваши записи: {meet}\n'
                             f'Время: {time}\n'
                             f'Дата: {date}', reply_markup=start_kb)
    else:
        await message.answer('У вас пока не записей', reply_markup=start_kb)
@user_router.message(F.text=='Профиль')
async def profil(message: types.Message):
    user_nickname = db.get_nickname(message.from_user.id)
    emp_type = db.get_employment_type(message.from_user.id)
    emp_type_text = 'Самозанятый' if emp_type == 'СЗ' else ('ИП' if emp_type == 'ИП' else 'Не указан')
    email = db.get_email(message.from_user.id) or 'Не указан'
    profile_text = f'Ваше имя: {user_nickname}\nСтатус занятости: {emp_type_text}\nEmail: {email}'
    await message.answer(profile_text, reply_markup=profile)


@user_router.message(F.text=='Предложить идею')
async def suggest_idea(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_text)
    await message.answer(
        'Расскажите нам об идее или о том, что хотелось бы улучшить в клубе / работе.\n\n'
        'P.S.: Также вы можете поделиться трудностями, с которыми столкнулись при использовании бота.\n\n'
        'Нажмите «Отмена», если передумали.',
        reply_markup=cancel_kb
    )


@user_router.message(IdeaState.waiting_text)
async def receive_idea(message: types.Message, state: FSMContext, bot: Bot):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.clear()
        await message.answer('Отменено.', reply_markup=profile)
        return
    user_id = message.from_user.id
    nickname = db.get_nickname(user_id) or message.from_user.full_name
    username = message.from_user.username
    header = f'💡 Предложение от {nickname}'
    if username:
        header += f' (@{username})'
    header += f' (id: {user_id})'
    idea_text = f'{header}\n\n{text}'
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, idea_text)
        except Exception as e:
            print(f'Ошибка отправки идеи админу {admin_id}: {e}')
    await message.answer('Спасибо! Идея отправлена разработчику.', reply_markup=profile)
    await state.clear()


@user_router.message(F.text=='Отменить запись')
async def no_zapis(message: types.Message, bot: Bot):
    zapis_na_vstrechy = db1.client_exists()
    nickname=db.get_nickname(message.from_user.id)
    if nickname in zapis_na_vstrechy:
        number_meet=db1.meet_by_client(nickname)
        await bot.send_message(676770835, f'{nickname} отменил запись на встречу №{number_meet}')
        zapis = db1.meet_by_client(nickname)
        null='None'
        status='Можно записаться'
        db1.add_zapis_meet(status, zapis)
        db.update_zapis(zapis, null)
        await message.answer('Запись отменена, не забудьте записаться на другое время!',reply_markup=start_kb)
    else:
        await message.answer('Записей пока нет(', reply_markup=start_kb)


@user_router.message(F.text=='Изменить имя')
async def changenick(message: types.Message, state: FSMContext):
    await message.answer('Напишите ваше ФИО (Фамилия Имя):', reply_markup=cancel_kb)
    await state.set_state(Registration.rename)


@user_router.message(Registration.rename)
async def changenick1(message: types.Message, state: FSMContext):
    text = (message.text or '').strip()
    if text.lower() == 'отмена':
        await state.clear()
        await message.answer('Действие отменено.', reply_markup=profile)
        return
    nickname = text
    if len(nickname.split())==2:
        if nickname.split()[0].isalpha()==True and nickname.split()[1].isalpha()==True:
            await state.update_data(rename=nickname)
            name=await state.get_data()
            nickname=name['rename']
            old_name=db.get_nickname(message.from_user.id)
            db.change_user_nickname(nickname, old_name)
            for names in db1.client_exists():
                if old_name==names:
                    db.change_nickname_in_meet(nickname, old_name)
            
            # Sync name change to Google Sheets
            if sheets_service and sheets_service.is_available():
                try:
                    await sheets_service.update_user_name(old_name, nickname)
                except Exception as e:
                    print(f"Error syncing name change to Sheets: {e}")
            
            await message.answer(f'Поздравляю! Теперь вас зовут {nickname}', reply_markup=profile)
            await state.clear()
        else:
            await message.answer('Вы должны использовать только символы киррилицы!')
            await state.set_state(Registration.rename)
    else:
        await message.answer('Введите фамилию и имя!')

@user_router.message(F.text=='Изменить статус занятости')
async def change_employment_type(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Самозанятый')],
            [KeyboardButton(text='ИП')],
            [KeyboardButton(text='Отмена')]
        ],
        resize_keyboard=True
    )
    await message.answer('Выберите ваш статус занятости:', reply_markup=kb)
    await state.set_state(Registration.change_employment_type)

@user_router.message(Registration.change_employment_type)
async def save_employment_type_change(message: types.Message, state: FSMContext):
    if message.text == 'Отмена':
        await state.clear()
        await message.answer('Действие отменено.', reply_markup=profile)
        return
    
    emp_type_text = message.text
    if emp_type_text not in ['Самозанятый', 'ИП']:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Самозанятый')],
                [KeyboardButton(text='ИП')],
                [KeyboardButton(text='Отмена')]
            ],
            resize_keyboard=True
        )
        await message.answer('Пожалуйста, выберите один из вариантов ниже', reply_markup=kb)
        return
    
    # Сохраняем как СЗ или ИП
    emp_type = 'СЗ' if emp_type_text == 'Самозанятый' else 'ИП'
    db.set_employment_type(message.from_user.id, emp_type)
    
    # Sync to Google Sheets
    if sheets_service and sheets_service.is_available():
        try:
            full_name = db.get_nickname(message.from_user.id)
            await sheets_service.update_user_employment_type(full_name, emp_type)
        except Exception as e:
            print(f"Error syncing employment type change to Sheets: {e}")
    
    await message.answer(f'Статус занятости изменен на: {emp_type_text}', reply_markup=start_kb)
    await state.clear()


@user_router.message(F.text=='Изменить почту')
async def change_email_prompt(message: types.Message, state: FSMContext):
    await message.answer(
        'Введите ваш новый email (например, user@example.com) или нажмите «Отмена»:',
        reply_markup=cancel_kb
    )
    await state.set_state(Registration.change_email)


@user_router.message(Registration.change_email)
async def change_email_save(message: types.Message, state: FSMContext):
    email = (message.text or '').strip()
    if email.lower() == 'отмена':
        await state.clear()
        await message.answer('Действие отменено.', reply_markup=start_kb)
        return
    if not _is_valid_email(email):
        await message.answer('Некорректный формат. Введите email вида user@example.com (или напишите "Отмена"):')
        return
    user_id = message.from_user.id
    db.set_email(user_id, email)
    if sheets_service and sheets_service.is_available():
        try:
            full_name = db.get_nickname(user_id)
            if full_name:
                await sheets_service.update_user_email(full_name, email)
        except Exception as e:
            print(f"Error syncing email change to Sheets: {e}")
    await message.answer('Email обновлён.', reply_markup=start_kb)
    await state.clear()


async def remind_missing_email(bot: Bot):
    user_ids = db.list_users_without_email()
    for user_id in user_ids:
        try:
            await bot.send_message(
                user_id,
                'Пожалуйста, добавьте актуальный email в профиле (кнопка «Изменить почту»).'
            )
        except Exception as e:
            print(f'Ошибка отправки напоминания об email пользователю {user_id}: {e}')

@user_router.message(F.text=='В меню')
@user_router.message(F.text=='Главное меню')
async def menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer('Перевожу вас в главное меню!', reply_markup=start_kb)


@user_router.message(F.text=='Добавить платеж')
async def add_payment_prompt(message: types.Message, state: FSMContext):
    await state.set_state(PaymentState.waiting_receipt)
    await message.answer(
        'Пришлите файл или фото с платежом. '
        'Если передумаете, нажмите "В меню".',
        reply_markup=back_kb
    )


def _payment_caption(message: types.Message = None, user_id: int = None, username: str = None, caption: str = None) -> str:
    """Формирует подпись для платежа."""
    if message:
        user_id = message.from_user.id
        username = message.from_user.username
        caption = message.caption
    
    nickname = db.get_nickname(user_id) if user_id else None
    if not nickname and message:
        nickname = message.from_user.full_name
    
    base = f'Платёж от {nickname}' if nickname else 'Платёж'
    if username:
        base += f' (@{username})'
    if caption:
        return f'{base}\n\n{caption}'
    return base


@user_router.message(PaymentState.waiting_receipt, F.photo | F.document)
async def handle_payment_upload(message: types.Message, state: FSMContext, bot: Bot):
    caption = _payment_caption(message)
    try:
        if message.document:
            await bot.send_document(
                SUPERS_GROUP_ID,
                message.document.file_id,
                caption=caption,
                message_thread_id=SUPERS_PAYMENTS_THREAD_ID
            )
        elif message.photo:
            await bot.send_photo(
                SUPERS_GROUP_ID,
                message.photo[-1].file_id,
                caption=caption,
                message_thread_id=SUPERS_PAYMENTS_THREAD_ID
            )
        await message.answer('Платёж отправлен супервайзерам.', reply_markup=start_kb)
        await state.clear()
    except Exception as e:
        await message.answer('Не удалось переслать платеж. Попробуйте позже или свяжитесь с администратором.')
        print(f'Ошибка пересылки платежа: {e}')


@user_router.message(PaymentState.waiting_receipt)
async def handle_payment_invalid(message: types.Message):
    await message.answer('Нужно отправить файл или фото платежа. Либо нажмите "В меню" для отмены.')


@user_router.message(F.photo | F.document)
async def handle_unsolicited_file(message: types.Message, state: FSMContext):
    """Обработка фото/файлов, отправленных без предварительного запроса."""
    # Проверяем, что пользователь не находится в состоянии ожидания оплаты
    current_state = await state.get_state()
    if current_state == PaymentState.waiting_receipt or current_state == PaymentState.asking_if_payment:
        return  # Пропускаем, если уже обрабатывается оплата
    
    # Сохраняем информацию о файле/фото
    file_data = {}
    if message.document:
        file_data = {
            'type': 'document',
            'file_id': message.document.file_id,
            'caption': message.caption
        }
    elif message.photo:
        file_data = {
            'type': 'photo',
            'file_id': message.photo[-1].file_id,  # Берем самое большое фото
            'caption': message.caption
        }
    
    # Сохраняем в состояние
    await state.update_data(file_data=file_data)
    await state.set_state(PaymentState.asking_if_payment)
    
    await message.answer(
        'Это оплата доступа в зал?',
        reply_markup=yes_no_kb
    )


@user_router.message(PaymentState.asking_if_payment, F.text == 'Да')
async def handle_payment_yes(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка подтверждения, что это оплата."""
    data = await state.get_data()
    file_data = data.get('file_data')
    
    if not file_data:
        await message.answer('Произошла ошибка. Попробуйте отправить файл снова.', reply_markup=start_kb)
        await state.clear()
        return
    
    # Формируем подпись с информацией о пользователе
    caption = _payment_caption(
        user_id=message.from_user.id,
        username=message.from_user.username,
        caption=file_data.get('caption')
    )
    
    try:
        if file_data['type'] == 'document':
            await bot.send_document(
                SUPERS_GROUP_ID,
                file_data['file_id'],
                caption=caption,
                message_thread_id=SUPERS_PAYMENTS_THREAD_ID
            )
        elif file_data['type'] == 'photo':
            await bot.send_photo(
                SUPERS_GROUP_ID,
                file_data['file_id'],
                caption=caption,
                message_thread_id=SUPERS_PAYMENTS_THREAD_ID
            )
        await message.answer('Платёж отправлен супервайзерам.', reply_markup=start_kb)
        await state.clear()
    except Exception as e:
        await message.answer('Не удалось переслать платеж. Попробуйте позже или свяжитесь с администратором.', reply_markup=start_kb)
        print(f'Ошибка пересылки платежа: {e}')
        await state.clear()


@user_router.message(PaymentState.asking_if_payment, F.text == 'Нет')
async def handle_payment_no(message: types.Message, state: FSMContext):
    """Обработка отказа, что это оплата."""
    await state.clear()
    await message.answer('Перевожу вас в главное меню!', reply_markup=start_kb)


@user_router.message(PaymentState.asking_if_payment)
async def handle_payment_question_invalid(message: types.Message):
    """Обработка некорректного ответа на вопрос об оплате."""
    await message.answer('Пожалуйста, выберите "Да" или "Нет".', reply_markup=yes_no_kb)


@user_router.message(F.text=='Записаться на встречу')
async def zapis(message: types.Message, state: FSMContext):
        zapis_na_vstrechy=db1.client_exists()
        if not(db.get_nickname(message.from_user.id) in zapis_na_vstrechy):
            meet = db1.name_meet1()
            message_to_answer = ''
            if len(meet)==0:
                await message.answer('Встреч пока нет, но скоро будут!')
            else:
                for names in range(0, len(meet) - 2, 4):
                    zapis = meet[names]
                    name = meet[names + 1]
                    time = meet[names + 2]
                    date = meet[names + 3]
                    if zapis=='Можно записаться':
                        message_to_answer += f'Встреча №{name}\nДата: {date}\nВремя: {time}\nСтатус: {zapis}\n'
                        message_to_answer += '\n'
                if len(message_to_answer)!=0:
                    await message.answer('Напишите номер встречи, на которую хотите записаться.\n')
                    await message.answer(message_to_answer, reply_markup=back_kb)
                    await state.set_state(SelectMeet.select_meet)
                else:
                    await message.answer('Доступных для записи встреч не обнаружено!', reply_markup=start_kb)
        else:
            await message.answer('Вы уже записаны на встречу, сначала отменитe запись!')


@user_router.message(SelectMeet.select_meet, F.text)
async def zapis(message: types.Message, state: FSMContext, bot: Bot):
    await state.update_data(select_meet=message.text)
    chose=message.text
    if db1.meet_exists(chose):
        if db.zapis_for_registration(chose)=='Можно записаться':
            status='Мест нет'
            meet= await state.get_data()
            zapis=meet['select_meet']
            user_name=db.get_nickname(message.from_user.id)
            db.zapis_meet(zapis,user_name)
            db1.add_zapis_meet(status, zapis)
            date = db1.select_date_client(user_name)
            date = date[user_name]
            time = db1.select_time_client(user_name)
            await message.answer(f'Вы успешно записаны на встречу №{chose} на {date} в {time}', reply_markup=start_kb)
            await bot.send_message(676770835, f'{user_name} записался на встречу №{zapis} на {date} в {time}')
            await state.clear()
        else:
            await message.answer('На эту встречу мест нет')
    else:
        await message.answer('Такой встречи нет(')


@user_router.message()
async def bot_message(message: types.Message):
        await message.answer('Не знаю чего вы хотите, идите лучше в главное меню\n\nЕсли это чек об оплате, нажмите кнопку «добавить платеж»', reply_markup=start_kb)