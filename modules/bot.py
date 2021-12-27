"""Module containing the code relating to the management of the Discord bot client."""

# Standard library imports
import asyncio
import datetime
import json

# Third-party imports
import discord
from discord.ext.tasks import loop

# Local application imports
from . import file_manager, commands, util, role_codes, member_ids, weekday_names, group_names, Emoji, Weekday
from .commands import help, homework, steam_market
from .util.web import InvalidResponseException
from .util.api import lucky_numbers as lucky_numbers_api, steam_market as steam_api
from .util.crawlers import lesson_plan as lesson_plan_crawler, substitutions as substitutions_crawler


class ChannelID:
    general: int = 766346477874053132
    nauka: int = 769098845598515220
    admini: int = 773137866338336768
    bot_testing: int = 832700271057698816
    bot_logs: int = 835561967007432784
    

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

my_server_id: int = 766346477874053130
prefix = '!'  # Prefix used before commands
enable_log_messages = True
use_bot_testing = False
restart_on_exit = True


def send_log(*raw_message, force=False) -> None:
    """Determine if the message should actually be logged, and if so, generate the string that should be sent."""
    if not (enable_log_messages or force):
        return

    msg = file_manager.log("test!", *raw_message)
    log_loop = asyncio.get_event_loop()
    log_loop.create_task(send_log_message(msg if len(msg) <= 4000 else f"Log message too long ({len(msg)} characters). Check 'bot.log' file."))


async def send_log_message(message) -> None:
    log_channel: discord.TextChannel = client.get_channel(ChannelID.bot_logs)
    await client.wait_until_ready()
    await log_channel.send(f"```py\n{message}\n```")


my_server: discord.Guild = None


# This function is called when the bot comes online
@client.event
async def on_ready() -> None:
    # Report information about logged in guilds
    guilds = {guild.id: guild.name for guild in client.guilds}
    send_log(f"Successfully connected as {client.user}.\nActive guilds:", guilds, force=True)
    
    # Initialise server reference
    global my_server
    my_server = client.get_guild(my_server_id)  # Konrad's Discord Server

    # Initialise lesson plan forcefully as bot loads; force_update switch bypasses checking for cache
    util.lesson_plan = lesson_plan_crawler.get_lesson_plan(force_update=True)[0]

    # Sets status message on bot start
    status = discord.Activity(type=discord.ActivityType.watching, name=get_new_status_msg())
    await client.change_presence(activity=status)

    # Starts loops that run continuously
    track_time_changes.start()
    track_api_updates.start()

    # Checks if the bot was just restarted
    for channel_id in [ChannelID.bot_testing, ChannelID.bot_logs]:
        channel = client.get_channel(channel_id)
        try:
            last_test_message = await channel.fetch_message(channel.last_message_id)
        except discord.errors.NotFound:
            send_log(f"Could not find last message in channel {channel.name}. It was probably deleted.")
        else:
            if last_test_message is None:
                send_log(f"Last message in channel {channel.name} is None.")
            elif last_test_message.author == client.user:
                if last_test_message.content == "Restarting bot...":
                    await last_test_message.edit(content="Restarted bot!")
            else:
                send_log(f"Last message in channel {channel.name} was not sent by me.")


# This function is called when someone sends a message in the server
@client.event
async def on_message(message: discord.Message) -> None:
    await client.wait_until_ready()
    if client.user in message.mentions:
        message.content = "!help " + message.content
    for reply in automatic_bot_replies:
        if reply.lower().startswith(message.content) and len(message.content) >= 3:
            await message.reply(automatic_bot_replies[reply], mention_author=False)
            return
    author_role_names = [str(role) for role in message.author.roles]
    if message.author == client.user or "Bot" in author_role_names or not message.content.startswith(prefix):
        return
    if not any(group_role in author_role_names for group_role in ["Grupa 1", "Grupa 2"]):
        await message.channel.send(
            f"{Emoji.warning} **Uwaga, {message.author.mention}: nie posiadasz rangi ani do grupy pierwszej "
            f"ani do grupy drugiej.\nUstaw sobie grupę, do której należysz reagując na wiadomość w kanale "
            f"{client.get_channel(773135499627593738).mention} numerem odpowiedniej grupy.**\n"
            f"Możesz sobie tam też ustawić język, na który chodzisz oraz inne rangi.")
    msg_first_word = message.content.lower().lstrip(prefix).split(" ")[0]
    admin_commands = ["exec", "restart", "quit", "exit"]
    if msg_first_word in admin_commands:
        if message.author != client.get_user(member_ids[8 - 1]):
            author_name = message.author.nick or message.author.name
            await message.reply(f"Ha ha! Nice try, {author_name}.")
            return
        if msg_first_word == admin_commands[0]:
            if not message.content.startswith(prefix + "exec "):
                await message.channel.send("Type an expression or command to execute.")
                return
            expression = message.content[len(prefix + "exec "):]
            send_log("Executing code:", expression)
            try:
                if "return " in expression:
                    exec(expression.replace("return ", "locals()['temp'] = "))
                else:
                    try:
                        exec(f"""locals()['temp'] = {expression}""")
                    except SyntaxError:
                        exec(expression)
                exec_result = locals()['temp'] if "temp" in locals() else "Code executed (return value not specified)."
            except Exception as e:
                exec_result = util.format_exception(e)
            if exec_result is None:
                await message.channel.send("Code executed.")
            else:
                expr = expression.replace("\n", "\n>>> ")
                result = exec_result
                if type(exec_result) in [dict, list]:
                    try:
                        result = "```\nDetected JSON content:```json\n" + json.dumps(exec_result, indent=4, ensure_ascii=False)
                    except (TypeError, OverflowError):
                        pass
                too_long_msg = f"Code executed:\n```py\n>>> {expr}```*Result too long to send in message, attaching file 'result.txt'...*"
                success_reply = f"Code executed:\n```py\n>>> {expr}\n{result}\n```"
                await try_send_message(message, False, {"content": success_reply }, exec_result, on_fail_msg=too_long_msg)
            return

        if msg_first_word == admin_commands[1]:
            await message.channel.send("Restarting bot...")
        else:
            await message.channel.send("Exiting program.")
            file_manager.log()
            file_manager.log(f"    --- Program manually closed by user ('{msg_first_word}' command). ---")
            global restart_on_exit
            restart_on_exit = False
        track_time_changes.stop()
        track_api_updates.stop()  
        await set_offline_status()
        await client.close()
        file_manager.log("Bot disconnected.")

    if msg_first_word not in help.info:
        return

    send_log(f"Received command: '{message.content}'", "from user:", message.author)
    callback_function = help.info[msg_first_word]["function"]
    try:
        reply_is_embed, reply = callback_function(message)
    except Exception as e:
        send_log(util.format_exception(e))
        await message.reply(f"<@{member_ids[8 - 1]}> An exception occurred while executing command `{message.content}`."
                            f" Check the bot logs for details.")
        return
    reply_msg = await try_send_message(message, True, {"embed" if reply_is_embed else "content": reply}, reply)
    if callback_function is homework.get_homework_events:
        await wait_for_zadania_reaction(message, reply_msg)


def get_new_status_msg(query_time: datetime.datetime = None) -> str:
    """Determine the current lesson status message.
    
    Arguments:
        query_time -- the time to get the status for.
    """
    # Default time to check is current time
    query_time = query_time or datetime.datetime.now()
    send_log(f"Updating bot status ...")
    next_period_is_today, next_period, next_lesson_weekday = commands.get_next_period(query_time)
    if next_period_is_today:
        # Get the period of the next lesson
        lesson = commands.get_lesson_by_roles(next_period % 10, next_lesson_weekday, list(role_codes.keys())[1:])
        if lesson:
            current_period = lesson['period']
            send_log("The next lesson is on period", lesson['period'])
        # Get the period of the first lesson
        for first_period, lessons in enumerate(util.lesson_plan[weekday_names[query_time.weekday()]]):
            if lessons:
                send_log("The first lesson is on period", first_period)
                break

        if next_period < 10:
            # Currently break time
            if current_period == first_period:
                # Currently before school
                new_status_msg = "szkoła o " + util.get_formatted_period_time(first_period).split('-')[0]
            else:
                new_status_msg = "przerwa do " + util.get_formatted_period_time(current_period).split('-')[0]
        else:
            # Currently lesson
            msgs: dict[str, str] = {}  # Dictionary with lesson group code and lesson name
            for role_code in list(role_codes.keys())[1:]:
                lesson = commands.get_lesson_by_roles(current_period, next_lesson_weekday, [role_code])
                if not lesson or lesson["period"] > current_period:
                    # No lesson for that group
                    send_log("Skipping lesson:", lesson, "on period", current_period)
                    continue
                send_log("Validated lesson:", lesson)
                msgs[lesson['group']] = commands.get_lesson_name(lesson['name'])
                # Found lesson for 'grupa_0' (whole class)
                if lesson['group'] == "grupa_0":
                    send_log("Found lesson for entire class, skipping checking individual groups.")
                    break
            # set(msgs.values()) returns a list of unique lesson names
            lesson_text = "/".join(set(msgs.values()))
            if len(msgs) == 1 and list(msgs.keys())[0] != "grupa_0":
                # Specify the group the current lesson is for if only one group has it
                lesson_text += " " + group_names[list(msgs.keys())[0]]
            new_status_msg = f"{lesson_text} do {util.get_formatted_period_time(current_period).split('-')[1]}"
    else:
        # After the last lesson for the given day
        current_period = -1
        new_status_msg = "koniec lekcji!" if query_time.weekday() < Weekday.friday else "weekend!"
    send_log(f"... new status message is '{new_status_msg}'.")
    return new_status_msg


async def remind_about_homework_event(event: homework.HomeworkEvent, tense: str) -> None:
    mention_text = "@everyone"  # To be used at the beginning of the reminder message
    event_name = event.title
    for role in role_codes:
        if role == event.group:
            mention_role = discord.utils.get(my_server.roles, name=role_codes[role])
            if role != "grupa_0":
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
            await message.edit(content=f"{Emoji.check_2} Zaznaczono zadanie `{event_name}` jako odrobione.")
        else:  # Reaction emoji is :alarm_clock:
            await snooze_event()
    await message.clear_reactions()
    file_manager.save_data_file()  # Updates data.json so that if the bot is restarted the event's parameters are saved


@loop(seconds=1)
async def track_time_changes() -> None:
    current_time = datetime.datetime.now()  # Today's time
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)  # Today's date + 1 day
    # Checks if current time is in list of key times
    if current_time.second == 0:
        if any([current_time.hour, current_time.minute] in times for times in util.lesson_plan["Godz"]):
            # Check is successful, bot updates Discord status
            status = discord.Activity(type=discord.ActivityType.watching, name=get_new_status_msg())
            await client.change_presence(activity=status)
    # Checks if the bot should make a reminder about due homework
    for event in homework.homework_events:
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


@loop(minutes=1)
async def track_api_updates() -> None:
    """Routinely fetches data from the various APIs in order to ensure it is up-to-date.
    Updates:
        - Steam Community Market item prices
        - The current lucky numbers from the SU ILO website
        - The substitutions from the I LO website
    """
    
    # Check if any tracked item's price has exceeded the established boundaries
    for item in steam_market.tracked_market_items:
        await asyncio.sleep(3)
        result = steam_api.get_item(item.name)
        price = steam_api.get_item_price(result)
        # Strips the price string of any non-digit characters and returns it as an integer
        price = int(''.join([char if char in "0123456789" else '' for char in price]))
        if item.min_price < price < item.max_price:
            continue
        target_channel = client.get_channel(ChannelID.bot_testing if use_bot_testing else ChannelID.admini)
        await target_channel.send(f"{Emoji.cash} Uwaga, <@{item.author_id}>! "
                                  f"Przedmiot *{item.name}* kosztuje teraz **{price/100:.2f}zł**.")
        steam_market.tracked_market_items.remove(item)
        file_manager.save_data_file()
    await asyncio.sleep(3)

    # Update the lucky numbers cache, and if it's changed, announce the new numbers in the specified channel.
    try:
        old_cache = lucky_numbers_api.update_cache()
    except InvalidResponseException as e:
        # Ping @Konrad
        await client.get_channel(ChannelID.bot_logs).send(f"<@{member_ids[8 - 1]}>")
        exc: str = util.format_exception(e)
        send_log(f"Error! Received an invalid response from the web request (lucky numbers cache update). Exception trace:\n{exc}")
    else:
        if old_cache != lucky_numbers_api.cached_data:
            send_log(f"New lucky numbers data!")
            target_channel = client.get_channel(ChannelID.bot_testing if use_bot_testing else ChannelID.general)
            await target_channel.send(embed=commands.lucky_numbers.get_lucky_numbers_embed()[1])
            file_manager.save_data_file()

    # Update the substitutions cache, and if it's changed, announce the new data in the specified channel.  
    try:
        old_cache = file_manager.cache_exists("subs")
        new_cache, cache_existed = substitutions_crawler.get_substitutions(True)
    except InvalidResponseException as e:
        # Ping @Konrad
        await client.get_channel(ChannelID.bot_logs).send(f"<@{member_ids[8 - 1]}>")
        exc: str = util.format_exception(e)
        send_log(f"Error! Received an invalid response from the web request (substitutions cache update). Exception trace:\n{exc}")
    else:
        if not cache_existed:
            send_log(f"Substitution data updated! New data:\n{new_cache}\n\nOld data:\n{old_cache}")
            target_channel = client.get_channel(ChannelID.bot_testing if use_bot_testing else ChannelID.general)
            # await target_channel.send(embed=get_substitutions_embed()[1])


@track_api_updates.before_loop
@track_time_changes.before_loop
async def wait_until_ready_before_loops() -> None:
    await client.wait_until_ready()


@track_time_changes.after_loop
async def set_offline_status() -> None:
    file_manager.log("Setting status to 'offline'.")
    offline_status = discord.Activity(status=discord.Status.offline)
    await client.change_presence(activity=offline_status)


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
        await reply_msg.edit(embed=homework.get_homework_events(message, True)[1])


async def try_send_message(user_message: discord.Message, should_reply: bool, send_args: dict, on_fail_data, on_fail_msg: str = None) -> discord.message:
    send_method = user_message.reply if should_reply else user_message.channel.send
    try:
        reply_msg = await send_method(**send_args)
    except discord.errors.HTTPException:
        send_log("Message too long. Length of data:", len(str(on_fail_data)))
        reply_msg = await send_method(on_fail_msg or "Komenda została wykonana pomyślnie, natomiast odpowiedź jest zbyt długa. Załączam ją jako plik tekstowy.")
        with open("result.txt", 'w') as file:
            if type(on_fail_data) is discord.Embed:
                on_fail_data = on_fail_data.to_dict()
            try:
                json.dump(on_fail_data, file, indent=2, ensure_ascii=False)
            except TypeError:
                file.write(str(on_fail_data))
        await user_message.channel.send(file=discord.File("result.txt"))
    return reply_msg