# TODO: This is a stub
def macro(first_arg, *remaining_args):
    if not remaining_args and callable(first_arg):
        return first_arg

    return macro
