"""Module containing code relating to the 'zad' command."""

# Standard library imports
import datetime

# Third-party imports
from discord import Message, Embed

# Local application imports
from . import HomeworkEvent, homework_events
from .. import bot, Emoji, file_manager, ROLE_CODES, GROUP_NAMES


DESC = """Tworzy nowe zadanie i automatycznie ustawia powiadomienie na dzień przed.
    Natomiast, jeśli w parametrach podane jest hasło 'del' oraz nr zadania, zadanie to zostanie usunięte.
    Parametry: __data__, __grupa__, __treść__ | 'del', __ID zadania__
    Przykłady:
    `{p}zad 31.12.2024 @Grupa 1 Zrób ćwiczenie 5` - stworzyłoby się zadanie na __31.12.2024__\
    dla grupy **pierwszej** z treścią: *Zrób ćwiczenie 5*.
    `{p}zad del 4` - usunęłoby się zadanie z ID: *event-id-4*."""
DESC_2 = "Pokazuje wszystkie zadania domowe, które zostały stworzone za pomocą komendy `{p}zad`."
DESC_3 = "Alias komendy `{p}zadanie` lub `{p}zadania`, w zależności od podanych argumentów."


def process_homework_events_alias(message: Message) -> tuple[bool, str or Embed]:
    args = message.content.split(" ")
    if len(args) == 1:
        return get_homework_events(message)
    elif len(args) < 4:
        return False, f"{Emoji.WARNING} Należy napisać po komendzie `{bot.prefix}zad` termin oddania zadania, oznaczenie " + \
            "grupy, dla której jest zadanie oraz jego treść, lub 'del' i ID zadania, którego się chce usunąć."
    return create_homework_event(message)


def get_homework_events(message: Message, should_display_event_ids=False) -> tuple[bool, str or Embed]:
    file_manager.read_data_file()
    amount_of_homeworks = len(homework_events)
    if amount_of_homeworks > 0:
        embed = Embed(title="Zadania", description=f"Lista zadań ({amount_of_homeworks}) jest następująca:")
    else:
        return False, f"{Emoji.INFO} Nie ma jeszcze żadnych zadań. " + \
               f"Możesz je tworzyć za pomocą komendy `{bot.prefix}zadanie`."

    # Adds an embed field for each event
    for homework_event in homework_events:
        group_role_name = ROLE_CODES[homework_event.group]
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
    embed.set_footer(text=f"Użyj komendy {bot.prefix}zadania, aby pokazać tą wiadomość.")
    return True, embed


def create_homework_event(message: Message) -> tuple[bool, str]:
    args = message.content.split(" ")
    # Args is asserted to have at least 4 elements
    if args[1] == "del":
        user_inputted_id = args[2].replace("event-id-", '')
        try:
            deleted_event = delete_homework_event(int(user_inputted_id))
        except ValueError:
            return False, f":x: Nie znaleziono zadania z ID: `event-id-{user_inputted_id}`. " + \
                          f"Wpisz `{bot.prefix}zadania`, aby otrzymać listę zadań oraz ich numery ID."
        return False, f"{Emoji.CHECK} Usunięto zadanie z treścią: `{deleted_event}`"
    try:
        datetime.datetime.strptime(args[1], "%d.%m.%Y")
    except ValueError:
        return False, f"{Emoji.WARNING} Drugim argumentem komendy musi być data o formacie: `DD.MM.YYYY`."
    title = args[3]
    for word in args[4:]:
        title += " " + word
    author = message.author.id
    if args[2] == "@everyone":
        group_id = "grupa_0"
        group_text = ""
    else:
        # Removes redundant characters from the third argument in order to have just the numbers (role id)
        group_id = int(args[2].lstrip("<&").rstrip(">"))
        try:
            message.guild.get_role(group_id)
        except ValueError:
            return False, f"{Emoji.WARNING} Trzecim argumentem komendy musi być oznaczenie grupy, dla której jest zadanie."
        group_text = GROUP_NAMES[group_id] + " "

    new_event = HomeworkEvent(title, group_id, author, args[1] + " 17")
    if new_event.serialised in homework_events:
        return False, f"{Emoji.WARNING} Takie zadanie już istnieje."
    new_event.sort_into_container(homework_events)
    file_manager.save_data_file()
    return False, f"{Emoji.CHECK} Stworzono zadanie na __{args[1]}__ z tytułem: `{title}` {group_text}" + \
                  "z powiadomieniem na dzień przed o **17:00.**"


def delete_homework_event(event_id: int) -> str:
    """Delete a homework event with the given ID.
    Returns the title of the deleted event.

    Raises ValueError if an event with the given ID is not found.
    """
    for event in homework_events:
        if event.id == event_id:
            homework_events.remove(event)
            file_manager.save_data_file()
            return event.title
    raise ValueError
