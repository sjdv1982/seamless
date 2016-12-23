#TODO: STUB!
import os

def fromfile(cell, filename):    
    import seamless
    seamless_lib_dir = os.path.realpath(os.path.split(seamless.lib.__file__)[0])
    new_filename = seamless_lib_dir + filename
    return cell.set(open(new_filename).read())
