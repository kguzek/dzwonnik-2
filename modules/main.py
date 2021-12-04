"""Dzwonnik 2, a Discord bot, by Konrad Guzek"""

# Standard library imports
import asyncio
import datetime
import importlib
import json
import math
import os
import traceback

# Third-party imports
import discord
from discord.ext import tasks

# Local application imports
if __name__ == "__main__":
    import file_management
    from constants import *
    from util import web_api, steam_api, lucky_numbers_api
else:
    file_management = importlib.import_module('modules.file_management')
    constants = importlib.import_module('modules.constants')
    # Import definitions to global namespace
    globals().update({k: getattr(constants, k) for k in constants.__dict__["__all__"]})
    web_api = importlib.import_module('modules.util.web_api')
    steam_api = importlib.import_module('modules.util.steam_api')
    lucky_numbers_api = importlib.import_module('modules.util.lucky_numbers_api')


intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
my_server = client.get_guild(766346477874053130)  # 2D The Supreme server


# This method is called when the bot comes online
@client.event
async def on_ready() -> None:
    global my_server
    guilds = {guild.id: guild.name for guild in client.guilds}
    attempt_debug_message(f"Successfully logged in as {client.user}\nActive guilds:", guilds, force=True)
    my_server = client.get_guild(766346477874053130)  # 1D The Supreme server

    # Sets status message on bot start
    status = discord.Activity(type=discord.ActivityType.watching, name=get_new_status_msg())
    await client.change_presence(activity=status)

    # Starts loops that run continuously
    track_time_changes.start()
    track_api_updates.start()

    # Checks if the bot was just restarted
    test_channel = client.get_channel(ChannelID.bot_testing)
    try:
        last_test_message = await test_channel.fetch_message(test_channel.last_message_id)
    except discord.errors.NotFound:
        attempt_debug_message("Could not find last message in bot-testing channel. It was probably deleted.")
    else:
        if last_test_message is not None and last_test_message.author == client.user:
            if last_test_message.content == "Restarting bot...":
                await last_test_message.edit(content="Restarted bot!")


class HomeworkEvent:
    def __init__(self, title, group, author_id, deadline, reminder_date=None, reminder_is_active=True):
        self.id = None
        self.title = title
        self.group = group
        self.author_id = author_id
        self.deadline = deadline.split(' ')[0]
        if reminder_date is None:
            reminder_date = datetime.datetime.strftime(datetime.datetime.strptime(
                deadline, "%d.%m.%Y %H") - datetime.timedelta(days=1), "%d.%m.%Y %H")
        self.reminder_date = reminder_date
        self.reminder_is_active = reminder_is_active

    @property
    def serialised(self):
        # Returns a dictionary with all the necessary data for a given instance to be able to save it in a .json file
        event_details = {
            'title': self.title,
            'group': self.group,
            'author_id': self.author_id,
            'deadline': self.deadline,
            'reminder_date': self.reminder_date,
            'reminder_is_active': self.reminder_is_active,
        }
        return event_details

    @property
    def id_string(self):
        # Returns a more human-readable version of the id with the 'event-id-' suffix
        return 'event-id-' + str(self.id)

    def sort_into_container(self, event_container):
        # Places the the event in chronological order into homework_events
        try:
            self.id = event_container[-1].id + 1
        except (IndexError, TypeError):
            self.id = 1
        # attempt_debug_message("Assigning ID", self.id, f"to event '{self.title}'")
        # attempt_debug_message("Sorting", self.id_string, "into container...")
        for comparison_event in event_container:
            new_event_time = datetime.datetime.strptime(self.deadline, "%d.%m.%Y")
            old_event_time = datetime.datetime.strptime(comparison_event.deadline, "%d.%m.%Y")
            # Dumps debugging data
            if new_event_time < old_event_time:
                # The new event should be placed chronologically before the one it is currently being compared to
                # Inserts event id in the place of the one it's being compared to, so every event
                # after this event (including the comparison one) is pushed one spot ahead in the list
                event_container.insert(event_container.index(comparison_event), self)
                # attempt_debug_message("Placed", self.id_string, "before", comparison_event.id_string)
                return
            # The new event should not be placed before the one it is currently being compared to, continue evaluating
        # At this point the algorithm was unable to place the event before any others, so it shall be put at the end
        event_container.append(self)
        # attempt_debug_message("Placed", self.id_string, "at the end of container")


class HomeworkEventContainer(list):
    @property
    def serialised(self):
        return [event.serialised for event in self]

    def remove_disjunction(self, reference_container):
        for event in self:
            if event.serialised not in reference_container.serialised:
                attempt_debug_message(f"Removing obsolete event '{event.title}' from container")
                self.remove(event)


class TrackedItem:
    def __init__(self, name, min_price, max_price, author_id):
        self.name = name
        self.min_price = min_price
        self.max_price = max_price
        self.author_id = author_id

    @property
    def serialised(self):
        return {
            "name": self.name,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "author_id": self.author_id
        }

    def __eq__(self, other):
        if type(other) is type(self):
            return self.name.lower() == other.name.lower()
        return False


# noinspection SpellCheckingInspection
lesson_names = {
    "rel": ["religia", "lookup/h2g6dftul7"],
    "gw": ["godzina wychowawcza", "lookup/ezg3aoqlpe"],
    "mat": ["matematyka", ""],
    "ang-1": ["język angielski", "lookup/bpwq26lzht"],
    "inf": ["informatyka", "lookup/f7mwatesda"],
    "edb": ["edukacja dla bezpieczeństwa", "lookup/daw4tvxftt"],
    "chem": ["chemia", "lookup/ccydofjmsy"],
    "geo": ["geografia", "lookup/dzuekigxx3"],
    "wos": ["wiedza o społeczeństwie", "lookup/flikhkjfkr"],
    "fiz": ["fizyka", "lookup/exacwjtr67"],
    "ang-kw": ["język angielski z p. Kwiatkowską", "lookup/bgz74rwodu"],
    "pol": ["język polski", "lookup/fthvbikyap"],
    "ang-2": ["język angielski", "lookup/fbrsxfud26"],
    "tok": ["theory of knowledge", "lookup/dpvw6r3mg7"],
    "wf": ["wychowanie fizyczne", "lookup/gb75o2kzx4"],
    "bio": ["biologia", "lookup/bhaw4bkiwa"],
    "dram": ["drama", "lookup/dzhxxxfabz"],
    "plas-1": ["plastyka", ""],
    "plas-2": ["plastyka", ""],
    "fr": ["język francuski", "xwa-ahgy-wns"],
    "es": ["język hiszpański", "fpv-tduz-ptc"],
    "de-1": ["język niemiecki", "otb-miyx-xfw"],
    "de-2": ["język niemiecki", "lookup/ggm2fxojv6"],
    "his": ["historia", "lookup/e5elwpevj5"],
    "chem-ks": ["zajęcia indywidualne z chemii", "lookup/ajgdbjndtv"],
    "separator": ["\u200b", " "]
}
prefix = '!'  # Prefix used before commands
enable_debug_messages = True
use_bot_testing = False
homework_events = HomeworkEventContainer()
tracked_market_items = []
restart_on_exit = True


def force_exit_program(dialog_box_message: str, dialog_box_title: str = "Dzwonnik 2 - Critical error") -> None:
    import sys
    from tkinter import Tk, messagebox
    window = Tk()
    window.wm_withdraw()
    messagebox.showerror(title=dialog_box_title, message=dialog_box_message)
    sys.exit("Program force-closed due to user error.")


def read_data_file(filename="data.json") -> None:
    global homework_events
    # Reads data file and updates settings
    if not os.path.isfile(filename):
        with open(filename, 'w') as file:
            default_settings = {
                "lesson_names": {},
                "homework_events": {},
                "tracked_market_items": [],
                "lucky_numbers": {}
            }
            json.dump(default_settings, file, indent=2)
    with open(filename, 'r', encoding="utf-8") as file:
        data = json.load(file)
    # We have defined lesson_names above, but this replaces any values that are different than the default
    lesson_names.update(data["lesson_names"])
    # homework_events.clear()  # To ensure there aren't any old instances, not 100% needed though
    # Creates new instances of the HomeworkEvent class with the data from the file
    new_event_candidates = HomeworkEventContainer()
    for event_id in data["homework_events"]:
        attributes = data["homework_events"][event_id]
        title, group, author_id, deadline, reminder_date, reminder_is_active = [attributes[attr] for attr in attributes]
        new_event_candidate = HomeworkEvent(title, group, author_id, deadline, reminder_date, reminder_is_active)
        new_event_candidates.append(new_event_candidate)
    homework_events.remove_disjunction(new_event_candidates)
    for new_event_candidate in new_event_candidates:
        if new_event_candidate.serialised not in homework_events.serialised:
            new_event_candidate.sort_into_container(homework_events)
    for item_attributes in data["tracked_market_items"]:
        item_name, min_price, max_price, author_id = [item_attributes[attr] for attr in item_attributes]
        item = TrackedItem(item_name, min_price, max_price, author_id)
        if item not in tracked_market_items:
            tracked_market_items.append(item)
    lucky_numbers_api.cached_data = data["lucky_numbers"]


def save_data_file(filename="data.json", should_send_debug_messages=True) -> None:
    """Saves the settings stored in the program's memory to the file provided.

    Arguments:
        filename -- the name of the file relative to the program root directory to write to (default 'data.json').
        should_send_debug_messages -- whether or not the save should be logged in the Discord Log and in the console.
    """
    if should_send_debug_messages:
        attempt_debug_message("Saving data file", filename)
    # Creates containers with the data to be saved in .json format
    serialised_homework_events = {event.id_string: event.serialised for event in homework_events}
    serialised_tracked_market_items = [item.serialised for item in tracked_market_items]
    # Creates a parent dictionary to save all data that needs to be saved
    data_to_be_saved = {
        "lesson_names": lesson_names,
        "homework_events": serialised_homework_events,
        "tracked_market_items": serialised_tracked_market_items,
        "lucky_numbers": lucky_numbers_api.cached_data
    }

    # Replaces file content with new data
    with open(filename, 'w') as file:
        json.dump(data_to_be_saved, file, indent=2)
    if should_send_debug_messages:
        attempt_debug_message(f"Successfully saved data file '{filename}'.")


def get_new_status_msg(query_time: datetime.datetime = None) -> str:
    """Determine the current lesson status message.
    Arguments:
        query_time -- the time to get the status for.
    """
    if query_time is None:
        # Default time to check is current time
        query_time = datetime.datetime.now()
    attempt_debug_message(f"Updating bot status ({query_time:%H:%M}) ...")
    if query_time.weekday() > 4:  # 0, 1, 2, 3, 4: Monday to Friday; > 4 means weekend
        attempt_debug_message("... it's currently the weekend.")
        new_status_msg = "weekend!"
    else:
        # Currently weekday
        next_period = get_next_period(query_time)
        next_period_is_today = next_period[2]
        if not next_period_is_today:
            new_status_msg = "koniec lekcji!"
        elif round(next_period[0]) == next_period[0]:  # Currently break time
            new_status_msg = "przerwa do " + timetable[math.floor(next_period[0])].split("-")[0]
        else:  # Currently lesson
            lesson_period = math.floor(next_period[0])
            lesson_group1 = get_lesson(lesson_period, next_period[1], [my_server.get_role(RoleID.gr1)])
            lesson_group2 = get_lesson(lesson_period, next_period[1], [my_server.get_role(RoleID.gr2)])
            lesson = lesson_group1[0][0]
            if lesson_group1 != lesson_group2:  # If both groups have different lessons
                lesson += "/" + lesson_group2[0][0]
            new_status_msg = f"{lesson} do {timetable[lesson_group1[2]].split('-')[1]}"
    return new_status_msg


async def remind_about_homework_event(event, tense) -> None:
    mention_text = "@everyone"  # To be used at the beginning of the reminder message
    event_name = event.title
    for role in role_ids:
        if role_ids[role] == event.group:
            mention_role = discord.utils.get(my_server.roles, name=role)
            if role != "everyone":
                mention_text = my_server.get_role(mention_role.id).mention
            break
    target_channel = client.get_channel(ChannelID.bot_testing if use_bot_testing else ChannelID.nauka)
    # Which tense to use in the reminder message
    when = {
        "today": "dziś jest",
        "tomorrow": "jutro jest",
        "past": f"{event.deadline} było",
        "future": f"{event.deadline} jest"  # 'future' is not really needed but I added it cause why not
    }[tense]  # tense can have a value of 'today', 'tomorrow' or 'past'
    message = await target_channel.send(f"{mention_text} Na {when} zadanie: **{event_name}**.")
    emojis = [Emoji.unicode_check, Emoji.unicode_alarm_clock]
    for emoji in emojis:
        await message.add_reaction(emoji)

    def check_for_valid_reaction(test_reaction, reaction_user):
        return reaction_user != client.user and str(test_reaction.emoji) in emojis

    async def snooze_event():
        new_reminder_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        event.reminder_date = new_reminder_time.strftime("%d.%m.%Y %H")
        await message.edit(content=":alarm_clock: Przełożono powiadomienie dla zadania `" +
                                   f"{event_name}` na {str(new_reminder_time.hour).zfill(2)}:00.")

    try:
        reaction, user = await client.wait_for('reaction_add', timeout=120.0, check=check_for_valid_reaction)
    except asyncio.TimeoutError:  # 120 seconds have passed with no user input
        await snooze_event()
    else:
        if str(reaction.emoji) == emojis[0]:
            # Reaction emoji is ':ballot_box_with_check:'
            event.reminder_is_active = False
            await message.edit(content=f":ballot_box_with_check: Zaznaczono zadanie `{event_name}` jako odrobione.")
        else:  # Reaction emoji is :alarm_clock:
            await snooze_event()
    await message.clear_reactions()
    save_data_file()  # Updates data.json so that if the bot is restarted the event's parameters are saved


@tasks.loop(seconds=1)
async def track_time_changes() -> None:
    current_time = datetime.datetime.now()  # Today's time
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)  # Today's time + 1 day
    # Checks if current time is in list of key times
    if f"{current_time:%H:%M}" in watch_times:
        # Check is successful, bot updates Discord status
        status = discord.Activity(type=discord.ActivityType.watching, name=get_new_status_msg())
        await client.change_presence(activity=status)
    # Checks if the bot should make a reminder about due homework
    for event in homework_events:
        reminder_time = datetime.datetime.strptime(event.reminder_date, "%d.%m.%Y %H")
        event_time = datetime.datetime.strptime(event.deadline, "%d.%m.%Y")
        # If this piece of homework has already had a reminder issued, ignore it
        if not event.reminder_is_active or reminder_time > current_time:
            continue
        if event_time.date() > tomorrow:
            tense = "future"
        elif event_time.date() == tomorrow:
            tense = "tomorrow"
        elif event_time.date() == current_time.date():
            tense = "today"
        else:
            tense = "past"
        await remind_about_homework_event(event, tense)


@tasks.loop(minutes=1)
async def track_api_updates() -> None:
    for item in tracked_market_items:
        await asyncio.sleep(3)
        result = steam_api.get_item(item.name)
        price = steam_api.get_item_price(result)
        # Strips the price string of any non-digit characters and returns it as an integer
        price = int(''.join([char if char in "0123456789" else '' for char in price]))
        if item.min_price < price < item.max_price:
            continue
        channel = client.get_channel(ChannelID.bot_testing)
        await channel.send(f":moneybag: Uwaga, <@{item.author_id}>! "
                           f"Przedmiot *{item.name}* kosztuje teraz **{price/100:.2f}zł**.")
        tracked_market_items.remove(item)
        save_data_file()
    await asyncio.sleep(3)
    data = lucky_numbers_api.get_lucky_numbers()
    if data != lucky_numbers_api.cached_data:
        attempt_debug_message(f"New data!\nOld data: {lucky_numbers_api.cached_data}\nNew data: {data}", force=True)
        lucky_numbers_api.cached_data = data
        channel = client.get_channel(ChannelID.bot_testing if use_bot_testing else ChannelID.general)
        await channel.send(embed=get_lucky_numbers()[1])
        save_data_file()


@track_api_updates.before_loop
@track_time_changes.before_loop
async def wait_until_ready_before_loops() -> None:
    await client.wait_until_ready()


# Times for the start and end of each period (0-9)
timetable = [
    "07:10-07:55",  # Period 0
    "08:00-08:45",  # Period 1
    "08:50-09:35",  # Period 2
    "09:45-10:30",  # Period 3
    "10:40-11:25",  # Period 4
    "11:35-12:20",  # Period 5
    "12:50-13:35",  # Period 6
    "13:40-14:25",  # Period 7
    "14:30-15:15",  # Period 8
    "15:20-16:05"   # Period 9
]

# List of times bot should update status for
watch_times = [time.split("-")[i] for time in timetable for i in range(2)]

# The following are timetables for each day
# Format: [lesson code, group ID, period]
lessons_monday = [
    ["bio", "grupa_0", 1],
    ["mat", "grupa_0", 2],
    ["wf", "grupa_0", 3],
    ["wf", "grupa_0", 4],
    ["ang-1", "grupa_1", 5],
    ["ang-2", "grupa_2", 5],
    ["pol", "grupa_0", 6],
    ["pol", "grupa_0", 7],
    ["rel", "grupa_rel", 8],
    ["rel", "grupa_rel", 9]
]

lessons_tuesday = [
    ["his", "grupa_0", 1],
    ["ang-1", "grupa_1", 2],
    ["ang-kw", "grupa_2", 2],
    ["ang-1", "grupa_1", 3],
    ["ang-2", "grupa_2", 3],
    ["pol", "grupa_0", 4],
    ["pol", "grupa_0", 5],
    ["mat", "grupa_0", 6],
    ["mat", "grupa_0", 7],
    ["tok", "grupa_0", 8]
]

lessons_wednesday = [
    ["geo", "grupa_0", 2],
    ["mat", "grupa_0", 3],
    ["chem", "grupa_0", 4],
    ["pol", "grupa_0", 5],
    ["pol", "grupa_0", 6],
    ["inf", "grupa_1", 7],
    ["ang-2", "grupa_2", 7],
    ["inf", "grupa_1", 8],
    ["ang-2", "grupa_2", 8]
]

lessons_thursday = [
    ["przed", "grupa_0", 1],
    ["chem", "grupa_1", 2],
    ["bio", "grupa_2", 2],
    ["bio", "grupa_1", 3],
    ["ang-2", "grupa_2", 3],
    ["his", "grupa_0", 4],
    ["wos", "grupa_0", 5],
    ["geo", "grupa_0", 6],
    ["wf", "grupa_0", 7],
    ["fiz", "grupa_0", 8]
]

lessons_friday = [
    ["chem", "grupa_2", 1],
    ["gw", "grupa_0", 2],
    ["ang-1", "grupa_1", 3],
    ["inf", "grupa_2", 3],
    ["ang-1", "grupa_1", 4],
    ["inf", "grupa_2", 4],
    ["fr", "grupa_fr", 5],
    ["es", "grupa_es", 5],
    ["de-1", "grupa_de1", 5],
    ["de-2", "grupa_de2", 5],
    ["fr", "grupa_fr", 6],
    ["es", "grupa_es", 6],
    ["de-1", "grupa_de1", 6],
    ["de-2", "grupa_de2", 6],
    ["mat", "grupa_0", 7],
    ["ang-kw", "grupa_1", 8],
    ["dram", "grupa_2", 8],
    ["dram", "grupa_1", 9]
]

# Table to easily identify which timetable to use for which day
# Eg. weekday is 0 (Monday) -> use item 0 of this list (lessons_monday)
# This means Saturday and Sunday (5 & 6) will use lessons_monday
weekday_tables = [
    lessons_monday,
    lessons_tuesday,
    lessons_wednesday,
    lessons_thursday,
    lessons_friday,
    lessons_monday,
    lessons_monday
]

# Which Discord role correlates to what group ID
role_ids = {
    "everyone": "grupa_0",
    "Grupa 1": "grupa_1",
    "Grupa 2": "grupa_2",
    "Religia": "grupa_rel",
    "Język Hiszpański": "grupa_es",
    "Język Francuski": "grupa_fr",
    "Język Niemiecki (Podstawa)": "grupa_de1",
    "Język Niemiecki (Rozszerzenie)": "grupa_de2"
}

# Dictionary with text to use when sending messages, eg. 'lekcja dla grupy drugiej'
group_names = {
    "grupa_0": "",
    "grupa_1": "dla grupy pierwszej",
    "grupa_2": "dla grupy drugiej",
    "grupa_rel": "dla grupy religijnej",
    "grupa_es": "dla grupy hiszpańskiej",
    "grupa_fr": "dla grupy francuskiej",
    "grupa_de1": "dla grupy niemieckiej z podstawą",
    "grupa_de2": "dla grupy niemieckiej z rozszerzeniem",
    "ks": "dla Krzysztofa Szatki"
}

# Table to keep results of calling get_lesson_plan_embed() method so that we don't have to calculate the result
# each time, since the it's always going to be the same for a given day
table_embed_cache = {}

weekday_names = [
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "poniedziałek",  # When get_next_lesson() is called on Saturday or Sunday,
    "poniedziałek"   # the program looks at Monday as the next school day.
]


# noinspection SpellCheckingInspection
member_ids = [
    693443232415088650,  # 01 Zofia Cybul
    695209819715403818,  # 02 Aleksandra Cywińska
    690174699459706947,  # 03 Ida Durbacz
    770552880791814146,  # 04 Pola Filipkowska
    773113923485827103,  # 05 Hanna Frej
    626494841865633792,  # 06 Adam Górecki
    622560689893933066,  # 07 Anna Grodnicka
    274995992456069131,  # 08 Konrad Guzek
    775676246566502400,  # 09 Aleksandra Izydorczyk
    690174919874576385,  # 10 Emilia Kiełkowska
    690171714025553924,  # 11 Maja Kierzkowska
    566344296001830923,  # 12 Zofia Kokot
    689859486172971082,  # 13 Stanisław Krakowian
    690171664062873721,  # 14 Daria Luszawska
    690275577835290684,  # 15 Martyna Marszałkowska
    770183107348529183,  # 16 Lena Masal
    692691918986936320,  # 17 Kalina Maziarczyk
    769604750898757662,  # 18 Mateusz Miodyński
    "Amelia Sapota",     # 19 Amelia Sapota
    770183024339714068,  # 20 Zofia Smołka
    770552880791814146,  # 21 Aleksandra Sobczyk
    626490320401596437,  # 22 Klara Sokół
    366955740260335646,  # 23 Krzysztof Szatka
    772888760340971531,  # 24 Iga Śmietańska
    635244325344772119,  # 25 Wojciech Tutajewicz
    770630571457380373,  # 26 Magdalena Wacławczyk
    694831920013639732,  # 27 Oliwia Wężyk
    715163616474693662,  # 28 Natalia Wcisło
    585427549216047104,  # 29 Paweł Żuchowicz
    712656114247794700,  # 20 Katarzyna Klos
    910219602552840202,  # 31 Patrycja Tustanowska
]


def create_homework_event(message: discord.Message) -> (bool, str):
    args = message.content.split(" ")
    # Args is asserted to have at least 4 elements
    if args[1] == "del":
        user_inputted_id = args[2].replace("event-id-", '')
        try:
            deleted_event = delete_homework_event(int(user_inputted_id))
        except ValueError:
            return False, f":x: Nie znaleziono zadania z ID: `event-id-{user_inputted_id}`. " + \
                          f"Wpisz `{prefix}zadania`, aby otrzymać listę zadań oraz ich numery ID."
        return False, f"{Emoji.check} Usunięto zadanie z treścią: `{deleted_event}`"
    try:
        datetime.datetime.strptime(args[1], "%d.%m.%Y")
    except ValueError:
        return False, f"{Emoji.warning} Drugim argumentem komendy musi być data o formacie: `DD.MM.YYYY`."
    title = args[3]
    for word in args[4:]:
        title += " " + word
    author = message.author.id
    # Removes redundant characters from the third argument in order to have just the numbers (role id)
    try:
        role_id = int(args[2].translate({ord(char): None for char in "<@&>"}))
        group_name = str(message.guild.get_role(role_id))
    except ValueError:
        if args[2] == "@everyone":
            group_name = "everyone"
        else:
            return False, ":warning: Trzecim argumentem komendy musi być oznaczenie grupy, dla której jest zadanie."
    group_id = role_ids[group_name]
    group_text = ' ' * (group_id != 'grupa_0') + group_names[group_id]

    new_event = HomeworkEvent(title, group_id, author, args[1] + " 17")
    if new_event.serialised in homework_events:
        return False, f":warning: Takie zadanie już istnieje."
    new_event.sort_into_container(homework_events)
    save_data_file()
    return False, f":white_check_mark: Stworzono zadanie na __{args[1]}__ z tytułem: `{title}`{group_text} " + \
                  "z powiadomieniem na dzień przed o **17:00.**"


def delete_homework_event(event_id: int) -> str:
    """Delete a homework event with the given ID.
    Returns the title of the deleted event.

    Raises ValueError if an event with the given ID is not found.
    """
    for event in homework_events:
        if event.id == event_id:
            homework_events.remove(event)
            save_data_file()
            return event.title
    raise ValueError


def get_homework_events(message: discord.Message, should_display_event_ids=False) -> (bool, str or discord.Embed):
    read_data_file()
    amount_of_homeworks = len(homework_events)
    if amount_of_homeworks > 0:
        embed = discord.Embed(title="Zadania", description=f"Lista zadań ({amount_of_homeworks}) jest następująca:")
    else:
        return False, f"{Emoji.info} Nie ma jeszcze żadnych zadań. " + \
               f"Możesz je tworzyć za pomocą komendy `{prefix}zadanie`."

    # Adds an embed field for each event
    for homework_event in homework_events:
        group_role_name = list(
            role_ids.keys())[list(role_ids.values()).index(homework_event.group)]
        role_mention = "@everyone"  # Defaults to setting @everyone as the group the homework event is for
        if group_role_name != "everyone":
            # Adjusts the mention string if the homework event is not for everyone
            for role in message.guild.roles:
                if str(role) == group_role_name:
                    # Gets the role id from its name, sets the mention text to a discord mention using format <@&ID>
                    role_mention = f"<@&{role.id}>"
                    break
        if homework_event.reminder_is_active:
            # The homework hasn't been marked as completed yet
            event_reminder_hour = homework_event.reminder_date.split(' ')[1]
            if event_reminder_hour == '17':
                # The homework event hasn't been snoozed
                field_name = homework_event.deadline
            else:
                # Show an alarm clock emoji next to the event if it has been snoozed (reminder time is not 17:00)
                field_name = f"{homework_event.deadline} :alarm_clock: {event_reminder_hour}:00"
        else:
            # Show a check mark emoji next to the event if it has been marked as complete
            field_name = f"~~{homework_event.deadline}~~ :ballot_box_with_check:"

        field_value = f"**{homework_event.title}**\n"\
                      f"Zadanie dla {role_mention} (stworzone przez <@{homework_event.author_id}>)"
        if should_display_event_ids:
            field_value += f"\n*ID: event-id-{homework_event.id}*"
        embed.add_field(name=field_name, value=field_value, inline=False)
    embed.set_footer(text=f"Użyj komendy {prefix}zadania, aby pokazać tą wiadomość.")
    return True, embed


def process_homework_events_alias(message: discord.Message) -> (bool, str or discord.Embed):
    args = message.content.split(" ")
    if len(args) == 1:
        return get_homework_events(message)
    elif len(args) < 4:
        return False, f":warning: Należy napisać po komendzie `{prefix}zad` termin oddania zadania, oznaczenie " + \
            "grupy, dla której jest zadanie oraz jego treść, lub 'del' i ID zadania, którego się chce usunąć."
    return create_homework_event(message)


def update_meet_link(message: discord.Message) -> (bool, str):
    if not message.channel.permissions_for(message.author).administrator:
        return False, ":warning: Niestety nie posiadasz uprawnień do korzystania z tej komendy."
    args = message.content.split(" ")
    if len(args) != 1:
        if args[1] in lesson_names:
            if len(args) == 2:
                lesson = lesson_names[args[1]][0]
                link = lesson_names[args[1]][1]
                return False, f"{Emoji.info} Link do Meeta dla lekcji " + \
                    f"'__{lesson}__' to <https://meet.google.com/{link}?authuser=0&hs=179>."
            else:
                link_is_dash_format = len(args[2]) == 12 and args[2][3] == args[2][8] == "-"
                link_is_lookup = len(args[2]) == 17 and args[2].startsWith("lookup/")
                if link_is_dash_format or link_is_lookup:  # User-given link is valid
                    old_link = lesson_names[args[1]][1]
                    lesson_names[args[1]][1] = args[2]
                    save_data_file()
                    return False, f":white_check_mark: Zmieniono link dla lekcji " \
                                  f"'__{lesson_names[args[1]][0]}__' z `{old_link}` na **{args[2]}**."
    msg = f"""Należy napisać po komendzie `{prefix}meet` kod lekcji, aby zobaczyć jaki jest ustawiony \
    link do Meeta dla tej lekcji, albo dopisać po kodzie też nowy link aby go zaktualizować.\nKody lekcji:```md"""
    for code, [name, link] in lesson_names.items():
        msg += f"\n# {code} [{name}]({link})"
    # noinspection SpellCheckingInspection
    msg += "```\n:warning: Uwaga: link do Meeta powinien mieć formę `xxx-xxxx-xxx` bądź `lookup/xxxxxxxxxx`."
    return False, msg


def get_help_message(_message: discord.Message) -> (bool, discord.Embed):
    embed = discord.Embed(title="Lista komend", description=f"Prefiks dla komend: `{prefix}`")
    for command_name, command_description in command_descriptions.items():
        if command_description is None:
            continue
        embed.add_field(name=command_name, value=command_description.format(p=prefix), inline=False)
    embed.set_footer(text=f"Użyj komendy {prefix}help lub mnie @oznacz, aby pokazać tą wiadomość.")
    return True, embed


def get_lesson_plan(message: discord.Message) -> (bool, str or discord.Embed):
    args = message.content.split(" ")
    if len(args) == 1:
        today = datetime.datetime.now().weekday()
        current_day = today if today < 5 else 0
    else:
        current_day = -1
        try:
            # This 'try' clause raises RuntimeError if the input is invalid for whatever reason
            try:
                # Check if the input is a number
                if not 1 <= int(args[1]) <= 5:
                    # It is, but of invalid format
                    raise RuntimeError(f"{args[1]} is not a number between 1 and 5.")
                else:
                    # It is, and of correct format
                    current_day = int(args[1]) - 1
            except ValueError:
                # The input is not a number.
                # Check if it is a day of the week
                for i, weekday in enumerate(weekday_names):
                    if weekday.startswith(args[1]):
                        # The input is a valid weekday name.
                        current_day = i
                        break
                if current_day == -1:
                    # The input is not a valid weekday name.
                    # ValueError can't be used since it has already been caught
                    raise RuntimeError(f"invalid weekday name: {args[1]}")
        except RuntimeError as e:
            attempt_debug_message(f"Handling exception with args: '{' '.join(args[1:])}' ({type(e).__name__}: \"{e}\")")
            return False, f"{Emoji.warning} Należy napisać po komendzie `{prefix}plan` numer dnia (1-5) " \
                          f"bądź dzień tygodnia, lub zostawić parametry komendy puste."
    sender_is_admin = message.channel.permissions_for(message.author).administrator
    if current_day + 5 * sender_is_admin not in table_embed_cache:
        loop_table = weekday_tables[current_day]
        periods = list(dict.fromkeys([lesson[-1] for lesson in loop_table]))
        lessons_per_period = [[lesson for lesson in loop_table if lesson[-1] == period] for period in periods]
        lesson_plan = [lessons_per_period, current_day, periods]
        embed = discord.Embed(
            title="Plan lekcji", description="Plan lekcji na **{d}** ({c} lekcji) jest następujący: ".format(
                d=weekday_names[lesson_plan[1]], c=len(periods)))
        for period in lesson_plan[2]:
            text = ""
            for lesson in lesson_plan[0][period - lesson_plan[2][0]]:
                if lesson[0] == "chem-ks" and (not sender_is_admin):
                    continue
                text += "[{p}](https://meet.google.com/{k}?authuser=0&hs=179) ".format(
                    p=lesson_names[lesson[0]][0], k=lesson_names[lesson[0]][1])
                if lesson[1] != "grupa_0":
                    text += "({g})".format(g=group_names[lesson[1]])
                if lesson != lesson_plan[0][period - lesson_plan[2][0]][-1]:
                    text += "\n"
            embed.add_field(name="Lekcja {p} ({t})".format(p=period, t=timetable[period]), value=text, inline=False)
        embed.set_footer(text="Użyj komendy {p}plan, aby pokazać tą wiadomość.".format(p=prefix))
        table_embed_cache[current_day + 5 * int(sender_is_admin)] = embed
    return True, table_embed_cache[current_day + 5 * sender_is_admin]


def get_next_period(given_time: datetime.datetime) -> (float, list[list[str or int]], bool):
    attempt_debug_message(f"Getting next period for {given_time:%x %X} ...")
    current_day_index: int = given_time.weekday()

    if current_day_index < 5:
        loop_table = weekday_tables[current_day_index]
        # Looks for any lesson that begins or ends after the specified time.
        for lesson in loop_table:
            lesson_period = lesson[-1]
            times = timetable[lesson_period].split("-")
            lesson_start_time = datetime.datetime.strptime(f"{given_time.strftime('%x')} {times[0]}", "%x %H:%M")
            if given_time < lesson_start_time:
                attempt_debug_message(f"... this is the break before period {lesson_period}.")
                return lesson_period, loop_table, True
            if given_time < lesson_start_time + datetime.timedelta(minutes=45):
                attempt_debug_message(f"... this is period {lesson_period}.")
                return lesson_period + 0.5, loop_table, True
        # Could not find any such lesson.
        next_school_day = current_day_index + 1
    else:
        # Monday the following week.
        next_school_day = 0

    # If it's currently weekend or after the last lesson on Friday
    loop_table = weekday_tables[next_school_day]
    attempt_debug_message("... there are no more lessons today.")
    first_period = loop_table[0][-1]
    return first_period, loop_table, False


# Returns the lesson details for a given period, day and user roles
def get_lesson(query_period, loop_table, roles) -> list:
    desired_roles = ["grupa_0"] + [role_ids[str(role)] for role in roles if str(role) in role_ids]
    for lesson_id, lesson_group, lesson_period in loop_table:
        if lesson_period >= query_period and lesson_group in desired_roles:
            return [lesson_names[lesson_id], group_names[lesson_group], lesson_period]
    attempt_debug_message(f"Did not find lesson for period {query_period} in loop table {loop_table}", force=True)
    return []


def get_datetime_from_input(message: discord.Message, calling_command: str) -> (bool, str or datetime.datetime):
    args = message.content.split(" ")
    current_time = datetime.datetime.now()
    if len(args) > 1:
        try:
            # Input validation
            try:
                if 0 <= int(args[1]) < 24:
                    if not 0 <= int(args[2]) < 60:
                        raise RuntimeError(f"Godzina ('{args[2]}') nie znajduje się w przedziale `0, 59`.")
                else:
                    raise RuntimeError(f"Minuta ('{args[1]}') nie znajduje się w przedziale `0, 23`.")
            except IndexError:
                # Minute not specified by user
                args.append(00)
            except ValueError:
                # NaN
                raise RuntimeError(f"`{':'.join(args[1:])}` nie jest godziną.")
        except RuntimeError as e:
            msg = f"{Emoji.warning} {e}\nNależy napisać po komendzie `{prefix}{calling_command}` godzinę" \
                  f" i ewentualnie minutę oddzieloną spacją, lub zostawić parametry komendy puste. "
            return False, msg
        current_time = current_time.replace(hour=int(args[1]), minute=int(args[2]), second=0, microsecond=0)
    return True, current_time


# Returns the message to send when the user asks for the next lesson
def get_next_lesson(message: discord.Message) -> (bool, str or discord.Embed):
    success, result = get_datetime_from_input(message, 'nl')
    if not success:
        return False, result
    current_time: datetime.datetime = result

    def process(time: datetime.datetime) -> (bool, str):
        next_period = get_next_period(time)
        lesson_details = get_lesson(math.floor(next_period[0]), next_period[1], message.author.roles)
        if not lesson_details:
            return False, f":x: Nie znaleziono żadnych lekcji dla Twojej grupy po godzinie {current_time:%H:%M}."
        if next_period[2]:
            # Currently lesson
            if math.ceil(next_period[0]) != next_period[0]:
                lesson_end_time = f"{current_time.strftime('%x')} {timetable[math.floor(next_period[0])].split('-')[1]}"
                # Get the next lesson after the end of this one, recursive call
                return process(datetime.datetime.strptime(lesson_end_time, "%x %H:%M"))
            next_period_time = timetable[lesson_details[2]].split("-")[0]
            group = lesson_details[1]
            if group != "":
                group += " "
            return True, f"{Emoji.info} Następna lekcja {group}to **{lesson_details[0][0]}** " \
                         f"o godzinie __{next_period_time}__.", lesson_details[0][1]
        else:
            if (current_time + datetime.timedelta(days=1)).weekday() == weekday_tables.index(next_period[1]):
                when = "jutro"
            else:
                when = "w poniedziałek"
            next_period_time = timetable[lesson_details[2]].split("-")[0]
            return True, f"{Emoji.info} Następna lekcja{lesson_details[1]} to **{lesson_details[0][0]}** " \
                         f"{when} o godzinie __{next_period_time}__.", lesson_details[0][1]

    success, *msg = process(current_time)
    if not success:
        return False, msg[0]

    description, link = msg
    embed = discord.Embed(title=f"Następna lekcja ({current_time:%H:%M})", description=description)
    embed.add_field(name="Link do lekcji", value=f"[meet.google.com](https://meet.google.com/{link}?authuser=0&hs=179)")
    embed.set_footer(text="Użyj komendy {p}nl, aby pokazać tą wiadomość.".format(p=prefix))
    return True, embed


# Calculates the time of the next break
def get_next_break(message: discord.Message) -> (bool, str):
    success, result = get_datetime_from_input(message, 'nb')
    if not success:
        return False, result
    current_time: datetime.datetime = result

    next_period = get_next_period(current_time)
    if next_period[2]:
        next_break_time = timetable[math.floor(next_period[0])].split("-")[1]
        msg = f"{Emoji.info} Następna przerwa jest o godzinie __{next_break_time}__."
    else:
        msg = f"{Emoji.info} Już jest po lekcjach!"
    return False, msg


def get_web_api_error_message(e: Exception) -> str:
    if type(e) is web_api.InvalidResponseException:
        return f"Nastąpił błąd w połączeniu: {e.status_code}"
    if type(e) is web_api.TooManyRequestsException:
        return f"Musisz poczekać jeszcze {3-e.time_since_last_request:.2f}s."
    if type(e) is steam_api.NoSuchItemException:
        return f":x: Nie znaleziono przedmiotu `{e.query}`. Spróbuj ponownie i upewnij się, że nazwa się zgadza."
    else:
        raise e


# Returns the message to send when the user asks for the price of an item on the Steam Community Market
def get_market_price(message: discord.Message, result_override=None) -> (bool, str):
    args: str = message.content.lstrip(f"{prefix}cena ").split(" waluta=") if result_override is None else [message]
    currency = args[-1] if len(args) > 1 else 'PLN'
    try:
        result = steam_api.get_item(args[0], 730, currency) if result_override is None else result_override
        return False, f"{Emoji.info} Aktualna cena dla *{args[0]}* to `{steam_api.get_item_price(result)}`."
    except Exception as e:
        return False, get_web_api_error_message(e)


# Returns the message to send when the user wishes to track an item on the Steam Community Market
def start_market_tracking(message: discord.Message):
    # noinspection SpellCheckingInspection
    args = message.content.lstrip(f"{prefix}sledz ").split(" min=")
    min_price = args[-1].split(" max=")[0].strip()
    max_price = args[-1].split(" max=")[-1].strip()
    try:
        min_price = int(float(min_price) * 100)
        max_price = int(float(max_price) * 100)
    except ValueError:
        # noinspection SpellCheckingInspection
        return False, f"{Emoji.warning} Należy wpisać po nazwie przedmiotu cenę minimalną oraz cenę maksymalną. " \
                      f"Przykład: `{prefix}sledz Operation Broken Fang Case min=1 max=3`."
    else:
        item_name = args[0].rstrip()
        try:
            result = steam_api.get_item(item_name)
        except Exception as e:
            return False, get_web_api_error_message(e)
        else:
            author_id = message.author.id
            item = TrackedItem(item_name, min_price, max_price, author_id)
            if item in tracked_market_items:
                for item in tracked_market_items:
                    if item.name.lower() == item_name.lower():
                        return False, f"{Emoji.warning} Przedmiot *{item.name}* jest już śledzony przez " + \
                               (f"użytkownika <@{item.author_id}>." if item.author_id != author_id else "Ciebie.")
            tracked_market_items.append(item)
            save_data_file()
            return False, f"{Emoji.check} Stworzono zlecenie śledzenia przedmiotu *{item_name}* w przedziale " \
                          f"`{min_price/100:.2f}zł - {max_price/100:.2f}zł`.\n" + \
                get_market_price(item_name, result_override=result)[1]


def stop_market_tracking(message: discord.Message) -> (bool, str):
    # noinspection SpellCheckingInspection
    item_name = message.content.lstrip(f"{prefix}odsledz ")
    for item in tracked_market_items:
        if item.name.lower() == item_name.lower():
            if item.author_id == message.author.id or message.channel.permissions_for(message.author).administrator:
                tracked_market_items.remove(item)
                save_data_file()
                return False, f"{Emoji.check} Zaprzestano śledzenie przedmiotu *{item.name}*."
            return False, f":x: Nie jesteś osobą, która zażyczyła śledzenia tego przedmiotu."
    return False, f":x: Przedmiot *{item_name}* nie jest aktualnie śledziony."


def get_lucky_numbers(*_message: tuple[discord.Message]) -> (bool, discord.Embed):
    data = lucky_numbers_api.cached_data
    msg = f"Szczęśliwe numerki na {data['date']}:"
    embed = discord.Embed(title="Szczęśliwe numerki", description=msg)
    for n in data["luckyNumbers"]:
        member_text = f"<@{member_ids[n - 1]}>" if n <= len(member_ids) else f"*Nie ma numerku {n} w naszej klasie.*"
        embed.add_field(name=n, value=member_text, inline=False)
    embed.add_field(name="\u200B", value="\u200B", inline=False)
    excluded_classes = ", ".join(data["excludedClasses"]) if len(data["excludedClasses"]) > 0 else "-"
    embed.add_field(name="Wykluczone klasy", value=excluded_classes, inline=False)
    embed.set_footer(text=f"Użyj komendy {prefix}numerki, aby pokazać tą wiadomość.")
    return True, embed


# noinspection SpellCheckingInspection
command_descriptions = {
    "help": "Wyświetla tą wiadomość.",

    "nl": """Mówi jaką mamy następną lekcję.
    Parametry: __godzina__, __minuta__
    Przykład: `{p}nl 9 30` - wyświetliłaby się najbliższa lekcja po godzinie 09:30.
    *Domyślnie pokazana jest najbliższa lekcja od aktualnego czasu*""",

    "nb": """Mówi kiedy jest następna przerwa.
    Parametry: __godzina__, __minuta__
    Przykład: `{p}nb 9 30` - wyświetliłaby się najbliższa przerwa po godzinie 09:30.
    *Domyślnie pokazana jest najbliższa przerwa od aktualnego czasu*""",

    "plan": """Pokazuje plan lekcji dla danego dnia.
    Parametry: __dzień tygodnia__
    Przykłady:
    `{p}plan` - wyświetliłby się plan lekcji na dziś/najbliższy dzień szkolny.
    `{p}plan 2` - wyświetliłby się plan lekcji na wtorek (2. dzień tygodnia).
    `{p}plan pon` - wyświetliłby się plan lekcji na poniedziałek.""",

    "zadanie": """Tworzy nowe zadanie i automatycznie ustawia powiadomienie na dzień przed.
    Natomiast, jeśli w parametrach podane jest hasło 'del' oraz nr zadania, zadanie to zostanie usunięte.
    Parametry: __data__, __grupa__, __treść__ | 'del', __ID zadania__
    Przykłady:
    `{p}zad 31.12.2024 @Grupa 1 Zrób ćwiczenie 5` - stworzyłoby się zadanie na __31.12.2024__\
    dla grupy **pierwszej** z treścią: *Zrób ćwiczenie 5*.
    `{p}zad del 4` - usunęłoby się zadanie z ID: *event-id-4*.""",

    "zadania": "Pokazuje wszystkie zadania domowe, które zostały stworzone za pomocą komendy `{p}zad`.",

    "zad": "Alias komendy `{p}zadanie` lub `{p}zadania`, w zależności od podanych argumentów.",

    "meet": None,

    "cena": """Podaje aktualną cenę dla szukanego przedmiotu na Rynku Społeczności Steam.
    Parametry: __przedmiot__, __waluta__
    Przykłady: 
    `{p}cena Operation Broken Fang Case` - wyświetliłaby się cena dla tego przedmiotu, domyślnie w zł.
    `{p}cena Operation Broken Fang Case waluta=EUR` - wyświetliłaby się cena dla tego przedmiotu w euro.""",

    "sledz": """Zaczyna śledzić dany przedmiot na Rynku Społeczności Steam \
    i wysyła powiadomienie, gdy cena wykroczy podaną granicę.
    Parametry: __nazwa przedmiotu__, __cena minimalna__, __cena maksymalna__,
    Przykład: `{p}sledz Operation Broken Fang Case min=1.00 max=3.00` - stworzyłoby się zlecenie śledzenia tego\
    przedmiotu z powiadomieniem, gdy cena się obniży poniżej 1,00zł lub przekroczy 3,00zł.""",

    "odsledz": """Przestaje śledzić dany przedmiot na Rynku Społeczności Steam.
    Parametry: __nazwa przedmiotu__
    Przykład: `{p}odsledz Operation Broken Fang Case` - zaprzestaje śledzenie ceny tego przedmiotu.""",

    "numerki": "Podaje aktualne szczęśliwe numerki oraz klasy, które są z nich wykluczone.",

    "num": "Alias komendy `{p}numerki`."
}
# noinspection SpellCheckingInspection
command_methods = {
    'help': get_help_message,
    'nl': get_next_lesson,
    'nb': get_next_break,
    'plan': get_lesson_plan,
    'zad': process_homework_events_alias,
    'zadanie': create_homework_event,
    'zadania': get_homework_events,
    'meet': update_meet_link,
    'cena': get_market_price,
    'sledz': start_market_tracking,
    'odsledz': stop_market_tracking,
    'numerki': get_lucky_numbers,
    'num': get_lucky_numbers
}

# noinspection SpellCheckingInspection
automatic_bot_replies = {
    "co jest?": "nie wjem"
}


async def wait_for_zadania_reaction(message: discord.Message, reply_msg: discord.Message) -> None:
    def check_for_valid_reaction(test_reaction, reaction_author):
        return str(test_reaction.emoji) == Emoji.unicode_detective and reaction_author != client.user

    await reply_msg.add_reaction(Emoji.unicode_detective)
    try:
        await client.wait_for('reaction_add', timeout=10.0, check=check_for_valid_reaction)
    except asyncio.TimeoutError:
        # 10 seconds have passed with no user input
        await reply_msg.clear_reactions()
    else:
        # Someone has added detective reaction to message
        await reply_msg.clear_reactions()
        await reply_msg.edit(embed=get_homework_events(message, True)[1])


# This method is called when someone sends a message in the server
@client.event
async def on_message(message: discord.Message) -> None:
    await client.wait_until_ready()
    if client.user in message.mentions:
        message.content = "!help " + message.content
    for reply in automatic_bot_replies:
        if reply.lower().startswith(message.content) and len(message.content) >= 3:
            await message.channel.send(automatic_bot_replies[reply])
            return
    author_role_names = [str(role) for role in message.author.roles]
    if message.author == client.user or "Bot" in author_role_names or not message.content.startswith(prefix):
        return
    if not any(group_role in author_role_names for group_role in ["Grupa 1", "Grupa 2"]):
        await message.channel.send(
            f":warning: **Uwaga, {message.author.mention}: nie posiadasz rangi ani do grupy pierwszej "
            f"ani do grupy drugiej.\nUstaw sobie grupę, do której należysz reagując na wiadomość w kanale "
            f"{client.get_channel(773135499627593738).mention} numerem odpowiedniej grupy.**\n"
            f"Możesz sobie tam też ustawić język, na który chodzisz oraz inne rangi.")
    msg_first_word = message.content.lower().lstrip(prefix).split(" ")[0]
    admin_commands = ["exec", "restart", "quit", "exit"]
    if message.channel.id in [ChannelID.bot_testing, ChannelID.bot_logs] and msg_first_word in admin_commands:
        if message.author != client.get_user(member_ids[7]):
            author_name = message.author.name if message.author.nick is None else message.author.nick
            await message.reply(f"Ha ha! Nice try, {author_name}.")
            return
        if msg_first_word == admin_commands[0]:
            code = message.content.replace('!', '', 1)[5:]
            attempt_debug_message("Executing code:", code)
            try:
                exec_result = exec(code)
            except Exception as e:
                exec_result = ' '.join(traceback.format_exception(type(e), e, e.__traceback__))
            if exec_result is not None:
                attempt_debug_message(">", exec_result)
            return

        if msg_first_word == admin_commands[1]:
            await message.channel.send("Restarting bot...")
        else:
            await message.channel.send("Exiting program.")
            print(f"\nProgram manually closed by user ('{msg_first_word}' command).\nGoodbye!\n")
            global restart_on_exit
            restart_on_exit = False

        track_time_changes.stop()
        track_api_updates.stop()
        await client.close()
    if msg_first_word not in command_descriptions:
        return
    # await message.delete()

    attempt_debug_message(f"Received command: '{message.content}'", "from user:", message.author)
    command_method_to_call_when_executed = command_methods[msg_first_word]
    try:
        reply_is_embed, reply = command_method_to_call_when_executed(message)
    except Exception as e:
        attempt_debug_message(traceback.format_exception(e))
        await message.reply(f"<@{member_ids[7]}> Exception occurred while executing command `{message.content}`."
                            f" Check the bot logs for details.")
        return
    if reply_is_embed:
        reply_msg = await message.reply(embed=reply)
    else:
        reply_msg = await message.reply(reply)

    if msg_first_word == "zadania":
        await wait_for_zadania_reaction(message, reply_msg)


def debug(*debug_message) -> None:
    attempt_debug_message(*debug_message, True)


def attempt_debug_message(*debug_message, time: datetime.datetime = None, force=False) -> None:
    if not enable_debug_messages and not force:
        return
    if time is None:
        time = datetime.datetime.now()
    timestamp = f"{time:%Y-%m-%d @ %H:%M:%S.%f}: "
    message = ' '.join(map(str, debug_message)).replace("\n", "\n" + " " * len(timestamp))
    debug_message_string = f"{timestamp}{message}"
    print(debug_message_string)
    log_loop = asyncio.get_event_loop()
    log_loop.create_task(send_debug_message(debug_message_string))


async def send_debug_message(debug_message) -> None:
    await client.wait_until_ready()
    await client.get_channel(ChannelID.bot_logs).send(f"```py\n{debug_message}\n```")


def start_bot() -> bool:
    """Log in to the Discord bot, and start its functionality.
    This method is blocking -- once the bot is connected, it will run until it's disconnected.

    Returns a boolean that indicates if the bot should be restarted.
    """
    # Update each imported module before starting the bot.
    # The point of restarting the bot is to update the code without having to manually stop and start the script.
    for module in (steam_api, web_api, lucky_numbers_api, file_management):
        importlib.reload(module)
    try:
        file_management.read_env_files()
        read_data_file('data.json')
        event_loop = asyncio.get_event_loop()
        try:
            token = os.environ["BOT_TOKEN"]
        except KeyError:
            print("\n'BOT_TOKEN' OS environment variable not found. Program exiting.\n")
            # Do not restart bot
            return False
        else:
            # No problems finding OS variable containing bot token. Can login successfully.
            event_loop.run_until_complete(client.login(token))

        try:
            # Blocking call:
            # The program will stay on this line until the bot is disconnected.
            event_loop.run_until_complete(client.connect())
        except KeyboardInterrupt:
            # Raised when the program is forcefully closed (eg. Ctrl+F2 in PyCharm).
            print("\nProgram manually closed by user.\nGoodbye!\n")
            # Do not restart, since the closure of the bot was specifically requested by the user.
            return False
        else:
            # The bot was exited gracefully (eg. !exit, !restart command issued in Discord)
            pass
    finally:
        # Execute this no matter the circumstances, ensures data file is always up-to-date.
        # The file is saved before the start_bot() method returns any value.
        # Do not send a debug message since the bot is already offline.
        save_data_file(should_send_debug_messages=False)
        print("Successfully saved data file 'data.json' (program exiting).\n")
    # By default, when the program is exited gracefully (see above), it is later restarted in run.pyw.
    # If the user issues a command like !exit, !quit, the return_on_exit global variable is set to False,
    # and the bot is not restarted.
    return restart_on_exit


if __name__ == "__main__":
    print("Started bot from main file! Assuming this is debug behaviour.\n")
    use_bot_testing = True
    enable_debug_messages = True
    start_bot()
