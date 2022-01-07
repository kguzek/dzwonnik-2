"""Module containing code relating to the 'help' command."""

# Third-party imports
from discord import Message, Embed

# Local application imports
from . import next_lesson, next_break, plan, homework, steam_market, lucky_numbers, substitutions
from . import meet, exec as execute, terminate
from .. import bot


def get_help_message(_: Message) -> tuple[bool, Embed]:
    """Event handler for the 'help' command."""
    desc = f"Prefiks dla komend: `{bot.prefix}`"
    embed = Embed(title="Lista komend", description=desc)
    for command_name, info in INFO.items():
        command_description = info["description"]
        if command_description:
            cmd_desc = command_description.format(p=bot.prefix)
            embed.add_field(name=command_name, value=cmd_desc, inline=False)
    footer = f"Użyj komendy {bot.prefix}help lub mnie @oznacz, aby pokazać tą wiadomość."
    embed.set_footer(text=footer)
    return True, embed


INFO: dict[help, dict[str, any]] = {
    "help": {
        "description": "Wyświetla tą wiadomość.",
        "function": get_help_message
    },
    "nl": {
        "description": next_lesson.DESC,
        "function": next_lesson.get_next_lesson
    },
    "nb": {
        "description": next_break.DESC,
        "function": next_break.get_next_break
    },
    "plan": {
        "description": plan.DESC,
        "function": plan.get_lesson_plan
    },
    "zad": {
        "description": homework.DESC,
        "function": homework.process_homework_events_alias
    },
    "zadanie": {
        "description": homework.DESC_2,
        "function": homework.create_homework_event
    },
    "zadania": {
        "description": homework.DESC_3,
        "function": homework.get_homework_events,
        "on_completion": homework.wait_for_zadania_reaction
    },
    "cena": {
        "description": steam_market.DESC,
        "function": steam_market.get_market_price
    },
    "sledz": {
        "description": steam_market.DESC_2,
        "function": steam_market.start_market_tracking
    },
    "odsledz": {
        "description": steam_market.DESC_3,
        "function": steam_market.stop_market_tracking
    },
    "numerki": {
        "description": lucky_numbers.DESC,
        "function": lucky_numbers.get_lucky_numbers_embed
    },
    "num": {
        "description": "Alias komendy `{p}numerki`.",
        "function": lucky_numbers.get_lucky_numbers_embed
    },
    "zast": {
        "description": substitutions.DESC,
        "function": substitutions.get_substitutions_embed
    },
    "meet": {
        "description": meet.DESC,
        "function": meet.update_meet_link
    },
    "exec": {
        "description": execute.DESC,
        "function": execute.execute_sync,
    },
    "exec_async": {
        "description": execute.DESC,
        "function": execute.execute_async,
        "on_completion": execute.run_async_code,
    },
    "restart": {
        "description": terminate.DESC,
        "function": terminate.restart_bot,
        "on_completion": terminate.terminate_bot,
    },
    "stop": {
        "description": terminate.DESC,
        "function": terminate.exit_bot,
        "on_completion": terminate.terminate_bot,
    },
    "exit": {
        "description": terminate.DESC,
        "function": terminate.exit_bot,
        "on_completion": terminate.terminate_bot,
    }
}