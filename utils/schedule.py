from __future__ import annotations

from typing import Optional

WEEKDAY_ALIASES = {
    'mon': ('mon', 0), 'monday': ('mon', 0), 'понедельник': ('mon', 0), 'пн': ('mon', 0),
    'tue': ('tue', 1), 'tuesday': ('tue', 1), 'вторник': ('tue', 1), 'вт': ('tue', 1),
    'wed': ('wed', 2), 'wednesday': ('wed', 2), 'среда': ('wed', 2), 'ср': ('wed', 2),
    'thu': ('thu', 3), 'thursday': ('thu', 3), 'четверг': ('thu', 3), 'чт': ('thu', 3),
    'fri': ('fri', 4), 'friday': ('fri', 4), 'пятница': ('fri', 4), 'пт': ('fri', 4),
    'sat': ('sat', 5), 'saturday': ('sat', 5), 'суббота': ('sat', 5), 'сб': ('sat', 5),
    'sun': ('sun', 6), 'sunday': ('sun', 6), 'воскресенье': ('sun', 6), 'вс': ('sun', 6),
}


def _parse_time_token(token: str) -> Optional[str]:
    token = token.strip()
    if not token:
        return None
    if ':' not in token:
        return None
    hour_part, minute_part = token.split(':', 1)
    try:
        hour = int(hour_part)
        minute = int(minute_part)
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _split_schedule(value: str) -> Optional[dict]:
    if value is None:
        return None
    text = ' '.join(value.strip().split())
    if not text:
        return None
    parts = text.split()
    if len(parts) == 1:
        time_part = _parse_time_token(parts[0])
        if not time_part:
            return None
        return {
            'type': 'daily',
            'time': time_part,
            'normalized': time_part,
        }
    if len(parts) != 2:
        return None
    prefix = parts[0].lower()
    time_part = _parse_time_token(parts[1])
    if not time_part:
        return None

    day_tokens = prefix.split(',')
    if all(t in WEEKDAY_ALIASES for t in day_tokens):
        codes = []
        weekdays = []
        for t in day_tokens:
            code, weekday = WEEKDAY_ALIASES[t]
            if code not in codes:
                codes.append(code)
                weekdays.append(weekday)
        return {
            'type': 'weekly',
            'weekday': weekdays[0],
            'weekdays': weekdays,
            'time': time_part,
            'normalized': f"{','.join(codes)} {time_part}",
        }
    if prefix.startswith('day='):
        try:
            day_value = int(prefix.split('=', 1)[1])
        except ValueError:
            return None
        if not (1 <= day_value <= 31):
            return None
        return {
            'type': 'monthly_day',
            'day': day_value,
            'time': time_part,
            'normalized': f"day={day_value} {time_part}",
        }
    if prefix == 'last':
        return {
            'type': 'monthly_last',
            'time': time_part,
            'normalized': f"last {time_part}",
        }
    if prefix.startswith('date='):
        try:
            month_str, day_str = prefix.split('=', 1)[1].split('-', 1)
            month = int(month_str)
            day_value = int(day_str)
        except ValueError:
            return None
        if not (1 <= month <= 12 and 1 <= day_value <= 31):
            return None
        return {
            'type': 'annual',
            'date': (month, day_value),
            'time': time_part,
            'normalized': f"date={month:02d}-{day_value:02d} {time_part}",
        }
    return None


def normalize_schedule_input(value: str) -> Optional[str]:
    """
    Normalize user input for notification schedule.

    Supported formats:
      - '10:00' (ежедневно)
      - 'mon 10:00' / 'пн 10:00' (дни недели)
      - 'day=6 10:00' (число месяца)
      - 'last 10:00' (последний день месяца)
      - 'date=08-23 09:00' (конкретная дата MM-DD)
    """
    result = _split_schedule(value)
    if not result:
        return None
    return result['normalized']


def parse_schedule_definition(value: str) -> Optional[dict]:
    """
    Parse stored schedule string into structured data.
    """
    return _split_schedule(value)

