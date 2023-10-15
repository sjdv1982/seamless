# Adapted from the Conda project (conda/main/conda/cli/common.py)
# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause

import sys

def confirm(message="Proceed", choices=("yes", "no"), default="yes"):
    assert default in choices, default

    options = []
    for option in choices:
        if option == default:
            options.append("[%s]" % option[0])
        else:
            options.append(option[0])
    message = "{} ({})? ".format(message, "/".join(options))
    choices = {alt: choice for choice in choices for alt in [choice, choice[0]]}
    choices[""] = default
    while True:
        # raw_input has a bug and prints to stderr, not desirable
        sys.stdout.write(message)
        sys.stdout.flush()
        try:
            user_choice = sys.stdin.readline().strip().lower()
        except OSError as e:
            raise RuntimeError(f"cannot read from stdin: {e}")
        if user_choice not in choices:
            print("Invalid choice: %s" % user_choice)
        else:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return choices[user_choice]


def confirm_yn(message="Proceed", default="yes"):
    try:
        choice = confirm(
            message=message, choices=("yes", "no"), default=default
        )
    except KeyboardInterrupt:  # pragma: no cover
        from .exceptions import SeamlessSystemExit

        raise SeamlessSystemExit("\nOperation aborted.  Exiting.")
    if choice == "no":
        from .exceptions import SeamlessSystemExit

        raise SeamlessSystemExit("Exiting.")
    return True

def confirm_yna(message="Proceed", default="yes"):
    try:
        choice = confirm(
            message=message, choices=("yes", "no", "all"), default=default
        )
    except KeyboardInterrupt:  # pragma: no cover
        from .exceptions import SeamlessSystemExit

        raise SeamlessSystemExit("\nOperation aborted.  Exiting.")
    if choice == "no":
        from .exceptions import SeamlessSystemExit

        raise SeamlessSystemExit("Exiting.")
    return choice
