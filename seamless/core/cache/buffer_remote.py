import os

_read_servers = None
_read_folders = None
_write_server = None
_initialized = False

_known_buffers = set()

def init():
    global _initialized
    # These variables have no defaults in seamless-fill-environment-variables
    # They are usually set by the Seamless assistant, or add_buffer_read_folder
    _known_buffers.clear()
    env = os.environ
    buffer_read_folders = env.get("SEAMLESS_BUFFER_READ_FOLDERS")
    buffer_read_servers = env.get("SEAMLESS_BUFFER_READ_SERVERS")
    buffer_write_server = env.get("SEAMLESS_BUFFER_WRITE_SERVER")
    '''
    if host is None:
        raise ValueError("environment variable SEAMLESS_DATABASE_IP not defined")
    port = env.get("SEAMLESS_DATABASE_PORT")
    if port is None:
        raise ValueError("environment variable SEAMLESS_DATABASE_PORT not defined")
    '''
    _initialized = True

def get_buffer(checksum):
    if _read_servers is None and _read_folders is None:
        return None
    raise NotImplementedError

def write_buffer(checksum, buffer):
    if _write_server is None:
        return
    # check has_buffer...
    # add to known buffers...
    raise NotImplementedError

def is_known(checksum):
    if checksum in _known_buffers:
        return True
    if _read_servers is not None:
        raise NotImplementedError
        # add to known buffers...
    if _read_folders is not None:
        raise NotImplementedError
        # add to known buffers...
    return False
    
def can_delete_buffer(checksum):
    if _write_server is not None:
        return True
    return is_known(checksum)    

def add_buffer_read_folder(path):
    raise NotImplementedError  #modify env var, init()
