"""
...
TODO: print mode (only direct_print)
You can switch from print mode to another mode, but not vice versa.
"""
from typing import OrderedDict
from seamless import core
import weakref
import os

python_attach_headers = {
    ("light", "vscode") : """Python source code mount to {host_path} detected.

In Visual Studio Code, set breakpoints in this file.""",

    ("full", "vscode") : """The source code has been mounted to files inside the directory:
{main_directory}.

In Visual Studio Code, set breakpoints in these files."""

}

python_attach_module_headers = {
    ("light", "vscode") : """Python module {module_name}: Python source code mount to {module_mount_path} detected.

In Visual Studio Code, set breakpoints in this file/directory.""",
}

python_attach_messages = {
    "vscode": """In "Run and Debug", an entry "{name}" should be present.
If not, make sure that {host_project_dir} is the primary directory of your VSCode workspace

Transformer execution will now be halted until the VSCode debugger attaches itself.

If the transformer is restarted by Seamless while the debugger is active, both will fail. 
In that case, do Transformer.clear_exception()"""

}

generic_attach_messages = {
    "vscode": """Generic source code mount to {host_path} detected.

In Visual Studio Code, set breakpoints in this file.
{object_mount_message}
In "Run and Debug", an entry "{name}" should be present.
If not, make sure that {host_project_dir} is the primary directory of your VSCode workspace

Transformer execution will now be halted until a SIGUSR1 signal is received.
Debugging is done in VSCore as follows:

- Press Ctrl+Shift+D, select the "{name}" debug entry and press F5.
- Press F6, then press Esc to ignore the "Cannot find select.c" error message
- Then press Ctrl+Shift+Y to go to the Debug Console
- Type "-exec signal SIGUSR1"
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

def get_compiled_mounted_module_objects(transformer):
    mmo = {}
    from ..highlevel import Cell
    node = transformer._get_htf()
    modulepath = tuple(node["path"]) + ("_main_module",)
    lp = len(modulepath)
    parent = transformer._parent()
    connections = parent._graph[1]
    for con in connections:
        if con["type"] != "connection":
            continue
        if con["target"][-1] != "code":
            continue
        if tuple(con["target"])[:lp] == modulepath:
            objectname = con["target"][-2]
            codecellpath = tuple(con["source"])
            try:
                codecell = parent._get_path(codecellpath)            
            except AttributeError:
                continue
            if not isinstance(codecell, Cell):
                break
            node = codecell._get_hcell()
            if node.get("UNTRANSLATED"):
                continue
            if "mount" in node:
                mmo[objectname] = node["mount"]["path"]
    return mmo

def find_transformer_modules(tf):
    from ..highlevel import Module
    modules = {}
    node = tf._get_htf()
    parent = tf._parent()
    connections = parent._graph[1]
    
    for pinname, pin in node["pins"].items():
        if pin.get("celltype") != "plain":
            continue
        if pin.get("subcelltype") != "module":
            continue
        modules[pinname] = None

        modulepinpath = tuple(node["path"]) + (pinname,)
        for con in connections:
            if con["type"] != "connection":
                continue
            if tuple(con["target"]) == modulepinpath:
                modulepath = tuple(con["source"])
                try:
                    module = parent._get_path(modulepath)            
                except AttributeError:
                    continue
                if not isinstance(module, Module):
                    break
                modules[pinname] = module
                break
    return modules

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
        self._enabled = False
        self._tf = weakref.ref(transformer)
        self._direct_print = False
        self._mode = None
        self._mount = None
        self._attach = True
        self._ide = "vscode"  # hard-coded for 0.7

    def _get_core_transformer(self, force):
        tf = self._tf()
        node = tf._get_htf()
        tf2 = tf._get_tf()
        if node["language"] == "python":
            return tf2.tf
        elif node["compiled"]:
            return tf2.tf.executor
        else:
            # bash, ipython, ipy_template, and py_bridge languages.
            # bash and py_bridge could be supported in the future
            if not force:
                return None  
            else:
                msg = """Attach-and-debug with breakpoints is not possible for language {}
Only shells in full debug mode are possible, please specify this explicitly"""
                raise ValueError(msg.format(node["language"]))

    def enable(self, mode=None):
        if self._enabled:
            raise ValueError("Debug mode is already active.")
        tf = self._tf()
        if tf is None or tf._get_htf().get("UNTRANSLATED"):
            raise ValueError("Transformer is untranslated.")
        if mode is None:
            mode = self._mode       
        if mode is not None:
            assert mode in ("full", "light"), mode
            if mode == "light":
                core_transformer = self._get_core_transformer(force=True)
                try:
                    validate_light_mode(self._tf())
                except ValidationError as exc:
                    reason = exc.args[0]
                    msg = """Cannot enter light debug mode. 
    Reason: {}"""
                    msg = msg.format(reason) + "\n"
                    raise ValidationError(msg) from None
            elif mode == "full":
                pass
        else:
            try:
                validate_light_mode(self._tf())
                mode = "light"
            except ValidationError as exc:
                reason = exc.args[0]
                msg = """Cannot enter light debug mode. 
Reason: {}"""
                print("*" * 80)
                print(msg.format(reason))
                print("*" * 80)
                mode = "full"

        if mode == "full":
            core_transformer = self._get_core_transformer(force=False)            
            self._mount = debugmountmanager.add_mount(
                core_transformer
            )
        elif mode == "light":
            core_transformer = self._get_core_transformer(force=True)
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
        if core_transformer is not None:
            core_transformer._debug = debug
            node = tf._get_htf()
            if node["compiled"]:
                tf._get_tf().tf.integrator.debug_.set(True)
            if core_transformer.status == "Status: OK":
                from ..core.manager.tasks.transformer_update import TransformerUpdateTask
                manager = core_transformer._get_manager()
                TransformerUpdateTask(manager, core_transformer).launch()                
        self._enabled = True

    @property
    def attach(self):
        """Debugger attach. 
If True, the transformer will wait for a debugger to attach"""
        return self._attach

    @attach.setter
    def attach(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(type(value))
        self._attach = value
        if self._enabled:
            debug = self._to_lowlevel(silent=True)
            core_transformer = self._get_core_transformer(force=False)
            if core_transformer is not None:
                on_off = "ON" if self._attach else "OFF"                
                print("Debugger attach is {}".format(on_off))
                core_transformer._debug = debug
            else:
                print("Debugger attach has changed: no effect on current debug mode")

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

    def _to_lowlevel(self, *, silent=False):
        debug = {
            "direct_print": self._direct_print,
            "python_attach": False,
            "python_attach_message": None,
            "generic_attach": False,
            "generic_attach_message": None,
        }
        mode = self._mode        
        if mode == "light":
            if not self._attach:
                raise ValueError("attach=False is pointless in light mode")
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
                hostcwd = os.environ.get("HOSTCWD")
                if hostcwd is not None: # source mapping is needed
                    host_path = os.path.relpath(code_path, "/cwd")
                    host_path = os.path.join(hostcwd, host_path)
                    host_project_dir = hostcwd
                    debug["source_map"] = [("/cwd", hostcwd)]
                debug["exec-identifier"] = code_path
                msg = python_attach_headers[mode, self._ide].format(
                    host_path=host_path,
                    host_project_dir=host_project_dir,
                    name=name
                ) + "\n"
                modules = find_transformer_modules(tf)
                module_mounts = {}
                for module_name, module in modules.items():
                    host_mount_path = None
                    mmsg = "Python module {module_name}: "
                    if module is None:
                        mmsg += "NOT CONNECTED"
                    else:
                        mount_path = None
                        module_mount = module._get_hnode().get("mount")
                        if module_mount is not None:
                            mount_path = module_mount.get("path")
                            mount_path = os.path.abspath(mount_path)
                        if mount_path is None:
                            mmsg += "NOT MOUNTED"
                        else:
                            ok = True                            
                            if hostcwd is not None: # source mapping is needed
                                if not mount_path.startswith("/cwd"):
                                    mmmsg = "code path {} does not start with /cwd, Seamless cannot do source mapping"
                                    mmsg += mmmsg.format(mount_path)
                                    ok = False
                                else:
                                    host_mount_path = os.path.relpath(mount_path, "/cwd")
                                    host_mount_path = os.path.join(hostcwd, host_mount_path)
                            if ok:
                                if module.multi:                        
                                    pass  # No special actions for multi-modules in light mode
                                module_mounts[module_name] = {
                                    "path": mount_path
                                }
                                mmsg = python_attach_module_headers[mode, self._ide]
                    msg += "\n" + mmsg.format(
                        module_name=module_name,
                        module_mount_path=host_mount_path
                    ) + "\n\n"
                msg += python_attach_messages[self._ide].format(
                    host_project_dir=host_project_dir,
                    name=name
                )
                if module_mounts:
                    debug["module_mounts"] = module_mounts
                debug["python_attach_message"] = msg
            elif node["compiled"]:
                debug["generic_attach"] = True
                code_path = os.path.abspath(code_mount["path"])
                host_path = code_path
                host_project_dir = os.getcwd()
                hostcwd = os.environ.get("HOSTCWD")
                if hostcwd is not None: # source mapping is needed
                    host_path = os.path.relpath(code_path, "/cwd")
                    host_path = os.path.join(hostcwd, host_path)
                    host_project_dir = hostcwd
                    debug["source_map"] = [("/cwd", hostcwd)]
                debug["mounted_module_objects"] = {
                    "main": code_path
                }
                mmo_ok = OrderedDict()
                mmo_not_ok = OrderedDict()
                mmo = get_compiled_mounted_module_objects(tf)
                object_mount_message = ""
                for objname in sorted(mmo.keys()):
                    objpath = mmo[objname]
                    ok = True
                    host_objpath = objpath
                    if hostcwd is not None: 
                        objpath2 = os.path.abspath(objpath)
                        if not objpath2.startswith("/cwd"):
                            ok = False
                        objpath3 = os.path.relpath(objpath2, "/cwd")
                        host_objpath = os.path.join(hostcwd, objpath3)                        
                    if ok:
                        debug["mounted_module_objects"][objname] = objpath
                        mmo_ok[objname] = host_objpath
                    else:
                        mmo_not_ok[objname] = host_objpath
                if mmo_ok:
                    object_mount_message += "\nA source mount was detected for the following code objects:\n"
                    for objname, host_objpath in mmo_ok.items():
                        object_mount_message += "- {} => {}\n".format(objname, host_objpath)
                    object_mount_message += "\n"
                if mmo_not_ok:
                    object_mount_message += """
A source mount cannot be used (filename does not start with /cwd)
for the following code objects:
"""
                    for objname, host_objpath in mmo_not_ok.items():
                        object_mount_message += "- {} => {}\n".format(objname, host_objpath)
                    object_mount_message += "\n"
                msg = generic_attach_messages[self._ide].format(
                    host_path=host_path,
                    host_project_dir=host_project_dir,
                    object_mount_message=object_mount_message,
                    name=name
                )
                debug["generic_attach_message"] = msg
        if mode == "full":
            tf = self._tf()
            debug["main_directory"] = self._mount.path
            if not silent:
                print("""Entering full debug mode for {}
Mounted main directory: {}
Debugger attach is {}            
""".format(tf, debug["main_directory"], "ON" if self._attach else "OFF"))
            debug["direct_print"] = True
            node = tf._get_htf()
            name = str(tf.path) + " Seamless transformer"
            debug["name"] = name
            host_project_dir = os.getcwd()
            hostcwd = os.environ.get("HOSTCWD")
            if hostcwd is not None:
                host_project_dir = hostcwd
            if node["language"] == "python":
                debug["python_attach"] = True
                msg = python_attach_headers[mode, self._ide].format(
                    main_directory=self._mount.path,
                    name=name
                ) + "\n"
                msg += python_attach_messages[self._ide].format(
                    host_project_dir=host_project_dir,
                    name=name
                )
                debug["python_attach_message"] = msg
                code_cell = getattr(self._mount.mount_ctx, "code")
                debug["exec-identifier"] = code_cell._mount["path"]
            else:            
                raise NotImplementedError

        if all([(f == False or f is None) for f in debug.values()]):
            return None
        debug["ide"] = self._ide
        debug["mode"] = mode
        debug["attach"] = self._attach    
        return debug

    @property
    def enabled(self):
        return self._enabled

    def pull(self):
        if not self._enabled:
            raise ValueError("Debug mode is not active.")
        if self._mode != "full":
            raise ValueError("Debug mode must be 'full'")
        tf = self._tf()
        if tf is not None:
            debugmount = tf._get_debugmount()
            return debugmount.pull()


    def disable(self):
        if not self._enabled:
            raise ValueError("Debug mode is not active.")
        tf = self._tf()
        if tf is None:
            return
        core_transformer = self._get_core_transformer(force=False)
        debugmountmanager.remove_mount(self._mount)
        if core_transformer is not None:
            from ..core.manager.tasks.transformer_update import TransformerUpdateTask
            core_transformer._debug = None
            node = tf._get_htf()
            if node["compiled"]:
                tf._get_tf().tf.integrator.debug_.set(False)
            manager = core_transformer._get_manager()
            TransformerUpdateTask(manager, core_transformer).launch()
        self._enabled = False

from .debugmount import debugmountmanager