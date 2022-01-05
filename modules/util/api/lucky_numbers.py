"""Functionality for getting the lucky numbers from the SU ILO website."""

# Standard library imports
from datetime import date, datetime
import json

from modules.bot import send_log

# Local application imports
from .. import web

# Data JSON structure:
# {
#     "date": "dd/mm/YYYY",
#     "luckyNumbers": [0, 0],
#     "excludedClasses": ["X", "Y"]
# }

# This module converts the date strings from the API into datetime.date objects
cached_data: dict[str, date or list[int or str]] = {}
max_cache_age = 1  # Days


def get_lucky_numbers() -> dict[str, str or list[int or str]]:
    """Updates the cache if it is outdated then returns it."""
    current_date: date = date.today()
    try:
        last_cache_date: date = cached_data["date"]
        if (current_date - last_cache_date).days > max_cache_age:
            raise ValueError()
    except (KeyError, ValueError):
        # If the cache is empty or too old
        update_cache()
    return cached_data


def update_cache() -> dict[str, str or list[int or str]]:
    """Updates the cache with current data from the SU ILO website.

    Returns the old cache so that it can be compared with the new one.
    """
    url = "https://europe-west1-lucky-numbers-suilo.cloudfunctions.net/app/api/luckyNumbers"
    global cached_data
    old_cache = cached_data
    cached_data = web.make_request(url, ignore_request_limit=True).json()
    if cached_data["date"]:
        data_timestamp: datetime = datetime.strptime(cached_data["date"], "%d/%m/%Y")
        cached_data["date"] = data_timestamp.date()
    return old_cache


def serialise(data: dict = cached_data):
    """Returns the cached data as a JSON-serialisable dictionary."""
    temp: dict = dict(data)
    for key, value in data.items():
        try:
            json.dumps(value)
        except (TypeError, OverflowError):
            temp[key] = str(value)
        except Exception as e:
            temp[key] = str(value)
            temp[type(e).__name__] = e
    return temp
