from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
admin_kb=ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text='Создать встречу'), KeyboardButton(text='Отменить/перенести')],
        [KeyboardButton(text='Все встречи'), KeyboardButton(text='Расписание встреч')],
        [KeyboardButton(text='Встречи на сегодня'), KeyboardButton(text='Удалить все встречи')],
        [KeyboardButton(text='Главное меню')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?')


change_kb=ReplyKeyboardMarkup(keyboard=[
          [KeyboardButton(text='Изменить время'),
            KeyboardButton(text='Изменить дату')],
            [KeyboardButton(text='Удалить встречу'),
            KeyboardButton(text='Назад')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?'
)


confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Да ✅"), KeyboardButton(text="Нет ❌")]
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?')


nachalo_kb=ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Работа со встречами'),
            KeyboardButton(text='Работа с тренерами')
        ],
        [KeyboardButton(text='Работа с уведомлениями')],
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?'
)


trener_kb=ReplyKeyboardMarkup(keyboard=[
          [KeyboardButton(text='Удалить тренера'), KeyboardButton(text='Изменить очередь')],
          [KeyboardButton(text='Данные тренеров')],
          [KeyboardButton(text='Главное меню')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?'
)

confirm_trainer_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Подтвердить ✅'), KeyboardButton(text='Отменить ❌')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Все верно?'
)


queue_days_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Понедельник'), KeyboardButton(text='Вторник')],
        [KeyboardButton(text='Среда'), KeyboardButton(text='Четверг')],
        [KeyboardButton(text='Пятница'), KeyboardButton(text='Суббота')],
        [KeyboardButton(text='Воскресенье'), KeyboardButton(text='Главное меню')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите день недели'
)


cancel_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Вы можете отменить действие'
)