import sys
from typing import OrderedDict
import weakref
import os
import asyncio

python_attach_headers = {
    ("light", "vscode") : """Python source code mount to {host_path} detected.

In Visual Studio Code, set breakpoints in this file.""",

    ("sandbox", "vscode") : """The source code has been mounted to files inside the directory:
{main_directory} .

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

If the transformer is restarted by Seamless while the debugger is active, both may fail. 
In that case, do Transformer.clear_exception()"""

}

generic_attach_messages = {
    "vscode": """Generic source code mount to {host_path} detected.

In Visual Studio Code, set breakpoints in this file/directory.
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
    if transformer.language == "bash":
        raise ValidationError("""Light debug mode does not make sense for a bash/docker transformer. 
Use sandbox mode instead.""")
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
        self._shellname = None

    def _get_core_transformer(self, force):
        tf = self._tf()
        node = tf._get_htf()
        tf2 = tf._get_tf()
        if tf2 is None:
            return None
        if node["language"] in ("python", "ipython"):
            return tf2.tf
        elif node["compiled"]:
            return tf2.tf.executor
        elif node["language"] == "bash":
            return tf2.tf
        else:
            # ipy_template and py_bridge languages.
            # py_bridge could be supported in the future
            if not force:
                return None  
            else:
                msg = "Attach-and-debug with breakpoints is not possible for language '{}'"
                raise ValueError(msg.format(node["language"]))

    def on_translate(self):
        if not self.enabled:
            if self.direct_print:
                tf = self._get_core_transformer(force=False)
                if tf is not None:
                    tf._debug = {"direct_print": True}

    def enable(self, mode, sandbox_name=None):
        if self._enabled:
            raise ValueError("Debug mode is already active.")
        tf = self._tf()
        node = tf._get_htf()
        if tf is None or node.get("UNTRANSLATED"):
            raise ValueError("Transformer is untranslated.")

        assert mode in ("sandbox", "light"), mode
        if mode == "sandbox":
            special = None
            if tf.language == "bash":
                special = "bash"
            elif node.get("compiled"):
                special = "compiled"        
            core_transformer = self._get_core_transformer(force=True)
            self._mount = debugmountmanager.add_mount(
                core_transformer, special=special, prefix=sandbox_name
            )
        elif mode == "light":
            try:
                validate_light_mode(tf)
            except ValidationError as exc:
                reason = exc.args[0]
                msg = """Cannot enter light debug mode. 
Reason: {}"""
                msg = msg.format(reason) + "\n"
                raise ValidationError(msg) from None

            core_transformer = self._get_core_transformer(force=True)
            code_mount = get_code_mount(tf)
            hostcwd = os.environ.get("HOSTCWD")
            code_path = os.path.abspath(code_mount["path"])
            if hostcwd is not None and not code_path.startswith("/cwd"):
                msg = """HOSTCWD is defined, but code path {} does not start with /cwd
Seamless cannot do source mapping. 
Only sandbox debug mode is possible."""
                raise ValidationError(msg.format(code_mount["path"]))
        self._mode = mode
        debug = self._to_lowlevel()
        if core_transformer is not None:
            core_transformer._debug = debug
            if node.get("compiled"):
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
            if value and self.mode == "sandbox":
                if self._mount.special == "bash":
                    raise ValidationError("Attach-and-debug with breakpoints is not supported for bash/docker transformers.")
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
                raise ValueError("attach=False is pointless in light debug mode")
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
        if mode == "sandbox":
            tf = self._tf()
            debug["main_directory"] = self._mount.path
            node = tf._get_htf()
            if not silent:
                print("""Entering sandbox debug mode for {}
Mounted main directory: {}""".format(tf, debug["main_directory"]))
                if node["language"] == "bash":
                    self._attach = False
                    print("""NOTE: The mounted files contents are synchronized with the Seamless sandbox, but they do NOT correspond with the files that the bash code sees
To create a directory where you can manually execute bash code, do Transformer.debug.shell()
""")
                else:
                    print("Debugger attach is {}".format("ON" if self._attach else "OFF"))
                    debug["direct_print"] = True            
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
                module_mounts = {}
                for module_name in self._mount.modules:
                    mod_code_cell = getattr(self._mount.mount_ctx, module_name)
                    mount_path = mod_code_cell._mount["path"]
                    module_mounts[module_name] = {
                        "path": mount_path
                    }
                if module_mounts:
                    debug["module_mounts"] = module_mounts
            elif node["compiled"]:
                assert "module" in self._mount.modules, self._mount.modules.keys()
                mounted_module_objects = {}
                for objname in self._mount._object_codes:
                    code_cell = getattr(self._mount.mount_ctx, objname)
                    module_name = objname[len(module_tag)+len("module."):]
                    code_path = code_cell._mount["path"]
                    mounted_module_objects[module_name] = code_path
                debug["mounted_module_objects"] = mounted_module_objects
                if self._attach:
                    debug["generic_attach"] = True
                    msg = generic_attach_messages[self._ide].format(
                        host_path=self._mount.path,
                        host_project_dir=host_project_dir,
                        object_mount_message="",
                        name=name
                    )
                    debug["generic_attach_message"] = msg
            elif node["language"] == "bash":
                # No attach of any kind...
                pass
            else:
                # TODO: ipython?
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
        if self._mode != "sandbox":
            raise ValueError("Debug mode must be 'sandbox'")
        tf = self._tf()
        if tf is not None:
            debugmount = tf._get_debugmount()
            return debugmount.pull()

    def _push_from_shell(self, inputname, value):
        if not self.enabled or self.mode != "sandbox":
            return
        c = getattr(self._mount.mount_ctx, inputname, None)
        if c is None:
            print("Cannot push '{}', not mounted as such".format(inputname))
        c.set(value) # observer should take care of the rest
        
    async def _new_shell(self):
        from ..core.cache.transformation_cache import transformation_cache
        from ..core.transformation import get_transformation_inputs_output
        tf = self._tf()
        ctf = self._get_core_transformer(force=True)
        tf_checksum = transformation_cache.transformer_to_transformations.get(ctf)
        transformation = transformation_cache.transformations[tf_checksum]
        if transformation is None:
            print("Cannot create shell for '{}': transformation does not exist", file=sys.stderr)
        io = get_transformation_inputs_output(transformation)
        inputs, outputname, _, _ = io
        if self._shellname is None: # No shells exist
            shellname0 = str(tf.path[1:])
            if tf.language == "bash":
                shellname = shellserver.new_bashshellhub(shellname0)
            elif tf.language in ("python", "ipython"):
                ipython_language = (tf.language == "ipython")
                shellname = shellserver.new_pyshellhub(
                    shellname0, inputs, outputname, ipython_language,
                    push_callback=self._push_from_shell

                )
            self._shellname = shellname 
        await shellserver.new_shell_from_transformation(
            self._shellname, transformation
        )

    def shell(self):
        if not self._enabled:
            raise ValueError("Debug mode is not active.")
        if self._mode != "sandbox":
            raise ValueError("Debug mode must be 'sandbox'")
        coro = asyncio.ensure_future(self._new_shell())
        if not asyncio.get_event_loop().is_running():
            asyncio.get_event_loop().run_until_complete(coro)

    def shells(self):
        if not self._enabled:
            raise ValueError("Debug mode is not active.")
        if self._mode != "sandbox":
            raise ValueError("Debug mode must be 'sandbox'")
        if self._shellname is None:
            return
        return shellserver.list_shells(self._shellname)

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
        if self._shellname is not None:
            shellserver.destroy_shellhub(self._shellname)
            self._shellname = None
        self._enabled = False

from .debugmount import debugmountmanager, module_tag
from .shellserver import shellserver