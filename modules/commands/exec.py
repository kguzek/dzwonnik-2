"""Module containing the code pertaining to the 'exec' command."""


# Standard library imports
import ast

# Third-party imports
import discord
from corny_commons import util as ccutil

# Local application imports
from modules import bot, util
from modules.commands import ensure_user_authorised


DESC = None
MISSING_ARGUMENTS_MSG = "Type an expression or command to execute."

# Initialise the code template to execute when the 'exec' command is called.
# Takes an argument of 'message' so that the object is available to the user for convenience.
EXPRESSION_TEMPLATE = "async def __execute(message):\n    {}\n    return locals()"


def inject_code(expression: str) -> str:
    """Attempts to inject code so that the evaluation result of the expression is saved in memory.

    Arguments:
        expression -- a string containing the raw code to be executed.

    Returns a string that may or may not contain injected code, depending on the input structure.
    """
    if "return " in expression:
        # Inject temporary variable storage in place of 'return' statements
        injection_snippet = "__temp += "
        expression = expression.replace("return ", injection_snippet)
        # If the user-inputted code contains a return statement, return the locals variable
        expression = expression.replace("return", "return locals()")
        expression = "__temp = util.ExecResultList()\n" + expression
    else:
        # No user-specified return value
        # Attempt to inject code so that the evaluation of the first line is returned
        try:
            # Check if such a code injection would be valid Python code
            ast.parse("_ = " + expression)
        except SyntaxError as syntax_error:
            # Code injection raises a syntax error; ignore it and don't inject code
            fmt_exc = ccutil.format_exception_info(syntax_error)
            bot.send_log(f"Caught SyntaxError in code injection:\n\n{fmt_exc}")
        else:
            # No syntax error; initialise the '__temp' local variable in code injection
            expression = "__temp = " + expression

    expression = EXPRESSION_TEMPLATE.format(expression.replace("\n", "\n    "))
    bot.send_log(f"Executing code:\n{expression}", force=True)
    return expression


async def process_execution(message: discord.Message) -> str:
    """Executes the code and returns the message that should be sent to the user.

    Returns the message that should be sent back directly to the user.
    """
    msg_content: str = message.content
    expression = msg_content.split(" ", maxsplit=1)[1]

    # Inject result-storing code to the user input and execute it.
    try:

        # Defines the '__execute()' function according to the template on line 22.
        # This raises any compile-time exceptions (such as SyntaxError).
        exec(inject_code(expression))  # pylint: disable=exec-used

        # The __execute() injected function returns its locals() dictionary.
        # This raises any run-time exceptions (such as ValueError).
        execute_locals: dict[str, any] = await locals()["__execute"](message) or {}
    except Exception as exec_exc:  # pylint: disable=broad-except
        # If the code logic is malformed or otherwise raises an exception, return the error info.
        exec_result = ccutil.format_exception_info(exec_exc)
    else:
        # Default the temp variable to an empty ExecResultList if it's not been assigned
        exec_result = execute_locals.get("__temp", util.ExecResultList())

        # Check if the results list is empty
        if isinstance(exec_result, util.ExecResultList) and not exec_result:
            return "*(return value unspecified)*"
    temp_variable_log_msg = f"Temp variable ({type(exec_result)}):\n{exec_result}"
    bot.send_log(temp_variable_log_msg, force=True)

    formatted_results = util.format_code_results(exec_result)

    return "\n".join(formatted_results)


def exec_command_handler(message: discord.Message) -> str:
    """Event handler for the 'exec' command."""
    msg_content: str = message.content
    args = msg_content.split(' ', maxsplit=1)
    ensure_user_authorised(message, owner_only=True)
    try:
        expression = args[1]
    except IndexError:
        return MISSING_ARGUMENTS_MSG
    fmt_expr = expression.replace("\n", "\n>>> ")
    return f"Code executing...\n```py\n>>> {fmt_expr}```"


async def execute_code(original_msg: discord.Message, reply_msg: discord.Message) -> None:
    """Callback function for the 'exec' command. Executes after the bot replies initially."""
    if reply_msg.content == MISSING_ARGUMENTS_MSG:
        return
    chnl: discord.TextChannel = reply_msg.channel
    async with chnl.typing():
        exec_result = await process_execution(original_msg)
    new_content = reply_msg.content.replace("executing...", "executed!")
    await reply_msg.edit(content=new_content)
    await bot.try_send_message(chnl, exec_result)
