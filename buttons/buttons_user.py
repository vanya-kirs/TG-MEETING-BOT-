from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
start_kb=ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Профиль'),
            KeyboardButton(text='Записаться на встречу'),
            KeyboardButton(text='Отменить запись'),
        ],
        [
            KeyboardButton(text='Добавить платеж'),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?'
)
profile=ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Изменить имя'),
            KeyboardButton(text='Изменить статус занятости'),
        ],
        [
            KeyboardButton(text='Изменить почту'),
        ],
        [
            KeyboardButton(text='Предложить идею'),
        ],
        [
            KeyboardButton(text='В меню'),
            KeyboardButton(text='Мои записи'),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?'
)

back_kb=ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='В меню'),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder='Чем могу быть полезен?'
)

cancel_kb=ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Отмена'),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder='Напишите текст или нажмите Отмена'
)

yes_no_kb=ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Да'),
            KeyboardButton(text='Нет'),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите ответ'
)

