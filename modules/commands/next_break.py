"""Module containing code relating to the 'nb' command."""

# Standard library imports
from datetime import datetime
from math import ceil

# Third-party imports
from discord import Message

# Local application imports
from .import get_datetime_from_input, get_lesson_by_roles, get_next_period
from ..import Emoji
from ..util import get_time, conjugate_numeric, send_log, get_formatted_period_time

# Calculates the time of the next break
def get_next_break(message: Message) -> tuple[bool, str]:
    success, result = get_datetime_from_input(message, 'nb')
    if not success:
        return False, result
    current_time: datetime = result

    next_period_is_today, lesson_period = get_next_period(current_time)[:2]

    if next_period_is_today:
        lesson = get_lesson_by_roles(lesson_period % 10, current_time.weekday(), message.author.roles)
        if not lesson:
            return False, f"{Emoji.info} Dzisiaj już nie ma dla Ciebie żadnych lekcji!"
        break_start_datetime = get_time(lesson['period'], current_time, True)
        break_countdown = break_start_datetime - current_time
        mins = ceil(break_countdown.seconds / 60)
        minutes = f"{(conjugate_numeric(mins // 60, 'godzin') + ' ') * (mins >= 60)}{conjugate_numeric(mins % 60, 'minut')}"
        msg = f"{Emoji.info} Następna przerwa jest za {minutes} o __{get_formatted_period_time(lesson['period']).split('-')[1]}"
        more_lessons_today, next_period = get_next_period(break_start_datetime)[:2]
        send_log("More lessons today:", more_lessons_today)
        if more_lessons_today:
            break_end_datetime = get_time(next_period, break_start_datetime, False)
            break_length = break_end_datetime - break_start_datetime
            msg += f"—{get_formatted_period_time(next_period).split('-')[0]}__ ({break_length.seconds // 60} min)."
        else:
            msg += "__ i jest to ostatnia przerwa."
    else:
        msg = f"{Emoji.info} Już jest po lekcjach!"
    return False, msg