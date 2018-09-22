from seamless.highlevel.Library import stdlib
from seamless.highlevel.Resource import Resource

import inspect
import os
def set_resource(f):
    caller_frame = inspect.currentframe().f_back
    filename = inspect.getfile(caller_frame)
    dirname = os.path.dirname(filename)
    ff = os.path.join(dirname, f)
    data = open(ff).read()
    if inspect.getmodule(caller_frame).__name__ == "__main__":
        return Resource(ff, data)
    else:
        return data

#from . import build_browser
