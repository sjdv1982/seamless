from typing import Any
from pathlib import Path
import os

from .message import message as msg


def guess_arguments_with_custom_error_messages(
    args: list[str],
    *,
    rule_ext_error_message,
    rule_no_ext_error_message,
    rule_no_slash_error_message,
    overrule_ext: bool = False,
    overrule_no_ext: bool = False,
) -> dict[str, Any]:
    """Guess for each argument if it represents a file, directory or value.

    In principle, for each argument,
     if it exists as a file/directory, it will be a file/directory, else a value.

    But there are three rules that must be respected, else an exception is raised.

    1. Any argument with extension must exist as a file, but not as a directory.
    2. Any argument (beyond the first) without extension must not exist as a file
       (directories are fine)
    3. Any argument ending with a slash must be a directory

    Input:
    - args: list of arguments

    - rule_ext_error_message: If rule 1. is violated, the ValueError message to raise.
    The message will be prepended with "Argument does not exist"
     or "Argument is a directory".
    It will then be formatted with "argindex" as the argument index (counting from 1)
    and "arg" as the argument string.

    - rule_no_ext_error_message: If rule 2. is violated, the ValueError message to raise.
    The message will be formatted with "argindex" as the argument index (counting from 1)
    and "arg" as the argument string.

    - rule_no_slash_error_message: If rule 3. is violated, the ValueError message to raise.
    The message will be prepended with "Argument does not exist"
     or "Argument is not a directory".
    It will then be formatted with "argindex" as the argument index (counting from 1)
    and "arg" as the argument string.

    - overrule_ext: if True, rule 1. does not apply.

    - overrule_no_ext: if True, rule 2. does not apply.
    """

    order = []

    result = {"@order": order}
    for argindex0, arg in enumerate(args):
        argindex = argindex0 + 1
        path = Path(arg)
        order.append(arg)
        extension = path.suffix
        msg(3, "Argument #{} '{}', extension: '{}'".format(argindex, arg, extension))
        exists = path.exists()
        is_dir = False
        if exists:
            is_dir = path.is_dir()

        # Rule 1.: Any argument with extension must exist as a file, but not as a directory.

        if not overrule_ext:
            if extension and not arg.endswith(os.sep):
                if not exists:
                    errmsg = "Argument does not exist.\n" + rule_ext_error_message
                    raise ValueError(errmsg.format(argindex=argindex, arg=arg))
                if is_dir:
                    errmsg = "Argument is a directory.\n" + rule_ext_error_message
                    raise ValueError(errmsg.format(argindex=argindex, arg=arg))

        # Rule 2.: Any argument (beyond the first) without extension must not exist as a file
        #          (directories are fine)
        if not overrule_no_ext:
            if argindex > 1 and not extension:
                if exists and not is_dir:
                    errmsg = rule_no_ext_error_message
                    raise ValueError(errmsg.format(argindex=argindex, arg=arg))

        # Rule 3.: Any argument ending with a slash must be a directory
        if arg.endswith(os.sep):
            if not exists:
                errmsg = "Argument does not exist.\n" + rule_no_slash_error_message
                raise ValueError(errmsg.format(argindex=argindex, arg=arg))
            if not is_dir:
                errmsg = "Argument is not a directory.\n" + rule_no_slash_error_message
                raise ValueError(errmsg.format(argindex=argindex, arg=arg))

        if exists:
            if is_dir:
                result[arg] = "directory"
            else:
                result[arg] = "file"
        else:
            result[arg] = "value"

    return result


def guess_arguments(
    args: list[str],
    *,
    overrule_ext: bool = False,
    overrule_no_ext: bool = False,
) -> dict[str, Any]:
    """Guess for each argument if it represents a file, directory or value.

    In principle, for each argument,
     if it exists as a file/directory, it will be a file/directory, else a value.

    But there are three rules that must be respected, else an exception is raised.

    1. Any argument with extension must exist as a file, but not as a directory.
    2. Any argument (beyond the first) without extension must not exist as a file
       (directories are fine)
    3. Any argument ending with a slash must be a directory

    Input:
    - args: list of arguments

    - overrule_ext: if True, rule 1. does not apply.

    - overrule_no_ext: if True, rule 2. does not apply.
    """

    rule_ext_error_message = """Argument #{argindex} '{arg}' has an extension.
Therefore, it must exist as a file.
To disable this rule, specify the -g1 option."""
    # TODO: add something in case of -c and ?/*
    rule_no_ext_error_message = """Argument #{argindex} '{arg}' has no extension.
Unless it is the first argument, it can't exist as a file.
To disable this rule, specify the -g2 option."""
    rule_no_slash_error_message = """Argument #{argindex} '{arg}' ends with a slash.
Therefore, it must be a directory."""

    return guess_arguments_with_custom_error_messages(
        args,
        overrule_ext=overrule_ext,
        overrule_no_ext=overrule_no_ext,
        rule_ext_error_message=rule_ext_error_message,
        rule_no_ext_error_message=rule_no_ext_error_message,
        rule_no_slash_error_message=rule_no_slash_error_message,
    )
