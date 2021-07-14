"""
...
You can switch from direct_print to another mode, but not vice versa.
"""
import weakref
import os


python_attach_messages = {
    "vscode": """Python source code mount to {host_path} detected.

In Visual Studio Code, set breakpoints in this file.

In "Run and Debug", an entry "{name}" should be present.
If not, make sure that {host_project_dir} is the primary directory of your VSCode workspace

Transformer execution will now be halted until the VSCode debugger attaches itself.

If the transformer is restarted by Seamless while the debugger is active, both will fail. 
In that case, do Transformer.clear_exception()"""

}

generic_attach_messages = {
    "vscode": """Python source code mount to {host_path} detected.

In Visual Studio Code, set breakpoints in this file.

In "Run and Debug", an entry "{name}" should be present.
If not, make sure that {host_project_dir} is the primary directory of your VSCode workspace

Transformer execution will now be halted until a SIGUSR1 signal is received.
Debugging is done as follows:

In VSCode, launch the "{name}" debug entry.
- Press F6, and press Esc to ignore the "Cannot find select.c" error message
- Then press Ctrl+Shift+Y, and type "-exec break".
- Type "-exec signal SIGUSR1"; again, press Esc to ignore the "Cannot find select.c" error message
- Finally, press F5
"""

}

class ValidationError(Exception):
    pass

def get_code_mount(transformer):
    from ..highlevel import Cell
    node = transformer._get_htf()
    if "mount" in node and "code" in node["mount"]:
        return node["mount"]["code"]
    codepath = tuple(node["path"]) + ("code",)
    parent = transformer._parent()
    connections = parent._graph[1]
    for con in connections:
        if con["type"] != "connection":
            continue
        if tuple(con["target"]) == codepath:
            codecellpath = tuple(con["source"])
            try:
                codecell = parent._get_path(codecellpath)            
            except AttributeError:
                continue
            if not isinstance(codecell, Cell):
                break
            node = codecell._get_hcell()
            if node.get("UNTRANSLATED"):
                msg = "Connected code cell {} is untranslated"
                raise ValidationError(msg.format(codecell))
            if "mount" in node:
                return node["mount"]

docker_container = None
docker_container_file = os.path.expanduser("~/DOCKER_CONTAINER")
if os.path.exists(docker_container_file):
    with open(docker_container_file) as f:
        docker_container = f.read().strip()
    
def validate_light_mode(transformer):
    env = os.environ
    hostcwd = env.get("HOSTCWD")
    if docker_container is not None and hostcwd is None:
        msg = """Running in a Docker container, but HOSTCWD is not defined.
Cannot do source mapping between container and host!"""
        raise ValidationError(msg)
    code_mount = get_code_mount(transformer)
    if code_mount is None:
        raise ValidationError("Code is not mounted, nor connected from a mounted cell")

class DebugMode:
    def __init__(self, transformer):
        self._tf = weakref.ref(transformer)
        self._direct_print = False
        self._mode = None
        self._ide = "vscode"  # hard-coded for 0.7

    def _get_core_transformer(self):
        tf = self._tf()
        node = tf._get_htf()
        tf2 = tf._get_tf()
        if node["language"] in ("python", "ipython"):
            return tf2.tf
        raise NotImplementedError

    def enable(self, mode=None):
        if self._mode is not None:
            raise ValueError("Debug mode is already active.")
        tf = self._tf()
        if tf is None or tf._get_htf().get("UNTRANSLATED"):
            raise ValueError("Transformer is untranslated.")
        core_transformer = self._get_core_transformer()
        if mode is not None:
            assert mode in ("full", "light"), mode
            if mode == "light":
                try:
                    validate_light_mode(self._tf())
                except ValidationError as exc:
                    reason = exc.args[0]
                    msg = """Cannot enter light debug mode. 
    Reason: {}"""
                    msg = msg.format(reason) + "\n"
                    raise ValidationError(msg) from None
        else:
            try:
                validate_light_mode(self._tf())
                mode = "light"
            except ValidationError as exc:
                reason = exc.args[0]
                msg = """Cannot enter light debug mode. 
Reason: {}
Entering full debug mode."""
                print("*" * 80)
                print(msg.format(reason))
                print("*" * 80)
                mode = "full"

        if mode == "full":
            code_mount = get_code_mount(tf)
            if code_mount["mode"] != "rw":
                msg = "Code mount '{}' must be read-write"
                raise Exception(msg.format(code_mount["path"]))
        elif mode == "light":
            code_mount = get_code_mount(tf)
            hostcwd = os.environ.get("HOSTCWD")
            code_path = os.path.abspath(code_mount["path"])
            if hostcwd is not None and not code_path.startswith("/cwd"):
                msg = """HOSTCWD is defined, but code path {} does not start with /cwd
Seamless cannot do source mapping. 
Only full debug mode is possible, please specify this explicitly"""
                raise ValidationError(msg.format(code_mount["path"]))
        self._mode = mode
        debug = self._to_lowlevel()
        core_transformer._debug = debug

    @property
    def mode(self):
        return self._mode
    
    @property
    def direct_print(self):
        """Causes the transformer to directly print any messages,
        instead of buffering them and storing them in Transformer.logs"""
        return self._direct_print

    @direct_print.setter
    def direct_print(self, value):
        if not isinstance(value, bool):
            raise TypeError(type(value))
        self._direct_print = value

    def _to_lowlevel(self):
        debug = {
            "direct_print": self._direct_print,
            "python_attach": False,
            "python_attach_message": None,
            "generic_attach": False,
            "generic_attach_message": None,
        }
        mode = self._mode
        if mode is not None:
            debug["direct_print"] = True
            tf = self._tf()
            node = tf._get_htf()
            code_mount = get_code_mount(tf)
            name = str(tf.path) + " Seamless transformer"
            debug["name"] = name
            if node["language"] == "python":
                debug["python_attach"] = True
                code_path = os.path.abspath(code_mount["path"])
                host_path = code_path
                host_project_dir = os.getcwd()
                if mode == "light": 
                    hostcwd = os.environ.get("HOSTCWD")
                    if hostcwd is not None: # source mapping is needed
                        host_path = os.path.relpath(code_path, "/cwd")
                        host_path = os.path.join(hostcwd, host_path)
                        host_project_dir = hostcwd
                        #debug["source_map"] = [(code_path, host_path)]
                        debug["source_map"] = [("/cwd", hostcwd)]
                    debug["exec-identifier"] = code_path
                msg = python_attach_messages[self._ide].format(
                    host_path=host_path,
                    host_project_dir=host_project_dir,
                    name=name
                )
                debug["python_attach_message"] = msg

        if all([(f == False or f is None) for f in debug.values()]):
            return None
        debug["ide"] = self._ide
        return debug
