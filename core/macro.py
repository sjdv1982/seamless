#STUB
def macro(*args):
    if len(args) == 1 and callable(args[0]):
        return args[0]
    return macro ###
