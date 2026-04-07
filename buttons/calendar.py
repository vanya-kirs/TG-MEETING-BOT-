from datetime import datetime
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton


from database.meet import Database1
db=Database1('fio.db')

months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
              'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

def month(date):
    return f'{months[int(date) - 1]}'


async def calendar_month():
    current_year=str(datetime.now().year)+' год'
    select_month=InlineKeyboardBuilder()
    select_month.add(InlineKeyboardButton(text=current_year, callback_data='year'))
    for mont in months:
        select_month.add(InlineKeyboardButton(text=mont, callback_data=f'{mont}'))
    return select_month.adjust(1,3).as_markup()


async def calendar_day(mont):
    mont=str(months.index(mont)+1)
    days_in_month_dict = {'1': 31, '2': 28,
                          '3': 31, '4': 30,
                          '5': 31, '6': 30,
                          '7': 31, '8': 31,
                          '9': 30, '10': 31,
                          '11': 30, '12': 31}
    weekdays_dict={0:'пн', 1:'вт',
                   2:'ср', 3:'чт',
                   4:'пт', 5:'сб',
                   6:'вс'}
    select_days=InlineKeyboardBuilder()
    len_month=days_in_month_dict[mont]
    current_year = str(datetime.now().year) + ' год'
    current_month=month(mont)
    datetime(int(datetime.now().year), int(mont), 1).weekday()
    select_days.add(InlineKeyboardButton(text=current_year, callback_data='year'))
    select_days.add(InlineKeyboardButton(text=current_month, callback_data='month'))
    for i in range(1,8):
        week_day=datetime(int(datetime.now().year), int(mont), i).weekday()
        select_days.add(InlineKeyboardButton(text=weekdays_dict[week_day], callback_data='weekday'))
    for days in range(1, len_month+1):
        select_days.add(InlineKeyboardButton(text=f'{days}', callback_data=f'{days}'))
    select_days.add((InlineKeyboardButton(text='назад', callback_data='назад')))
    return select_days.adjust(2,7).as_markup()


async def calendar_time(data, dobavlen=None):
    hours=['09','10','11','12','13','14','15','16','17','18','19','20']
    minutes=['00', '20', '40']
    select_time=InlineKeyboardBuilder()
    time_db = db.time_meet1(data)
    if dobavlen is not None:
        for hour in hours:
            for minute in minutes:
                time=hour+':'+minute
                if time in dobavlen:
                    if time not in time_db:
                        select_time.add(InlineKeyboardButton(text=f'{time}✅', callback_data=f'{time}'))
                else:
                    if time not in time_db:
                        select_time.add(InlineKeyboardButton(text=time, callback_data=f'{time}'))
    else:
        for hour in hours:
            for minute in minutes:
                time=hour+':'+minute
                if time not in time_db:
                    select_time.add(InlineKeyboardButton(text=time, callback_data=f'{time}'))
    select_time.add(InlineKeyboardButton(text='назад', callback_data='назад'))
    select_time.add(InlineKeyboardButton(text='создать встречи', callback_data='создать встречи'))
    return select_time.adjust(4).as_markup()