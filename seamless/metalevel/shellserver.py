import asyncio
import inspect
import logging
import multiprocessing
from queue import Empty
import subprocess
import sys
import textwrap
import time
import traceback
import os
from multiprocessing.context import Process

import os,shutil
import tempfile
from typing import OrderedDict
import numpy as np
import json
from silk import Silk
from silk.mixed.get_form import get_form

DOCKER_CONTAINER = None
docker_container_file = os.path.expanduser("~/DOCKER_CONTAINER")
if os.path.exists(docker_container_file):
    with open(docker_container_file) as f:
        DOCKER_CONTAINER = f.read().strip()

PYMESSAGE = """**********************************************************************
Seamless IPython shell {name} started.

The shell contains the *current* values of the code and inputs
of the debugged transformer sandbox. The shell is not auto-synchronized with
the sandbox. 

In a bash terminal, you can connect to the shell with:
  {CONSOLE_COMMAND} {connection_file}
**********************************************************************
"""

PYBANNER = """**********************************************************************
Seamless IPython shell {name}.

The shell contains the *current* values of the code and inputs
of the debugged transformer sandbox ".{name}". 
The shell is not synchronized with value updates from elsewhere. 

In the shell, you can:
- Execute the transformation with "transform()"
- Access and modify the transformation's code or any of its inputs
- Push modified code or inputs back to the debugged transformer,
  using "push('code')" or "push(input name)"
- Kill the shell with "quit()"

**********************************************************************
"""

BASHMESSAGE = """**********************************************************************
Seamless bash shell directory {name}.

The shell directory contains the *current* values of the code and inputs
of the debugged transformer sandbox ".{name}". 

To access it, open a bash terminal and do:

  {bash_command}

Then do:

  source ./ENVIRONMENT.sh

to load the transformer's pin environment variables.

The bash code is written to "transform.sh"
The other file names in the shell directory correspond to the pin names, 
as expected by the bash code. 
The files are not synchronized with the files in the sandbox directory. 

**********************************************************************
"""

import os, tempfile

DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE")
if DOCKER_IMAGE is None and DOCKER_CONTAINER is None:
    CONSOLE_COMMAND = "jupyter console --existing"
else:
    CONSOLE_COMMAND = "seamless-jupyter-console-existing"
    if DOCKER_CONTAINER is not None:
        CONSOLE_COMMAND += " --container {}".format(DOCKER_CONTAINER)
    elif DOCKER_IMAGE != "rpbs/seamless":
        CONSOLE_COMMAND += " --image {}".format(DOCKER_IMAGE)
    CONSOLE_COMMAND += " --existing"


class ShellDict(dict):
    def __init__(self,
        name,
        push_queue, inputs:list, *,
        output_name,
        ipython_language:bool
    ):
        self._name = name
        self._inputs = inputs
        self._push_queue = push_queue
        self._output_name = output_name
        self._ipython_language = ipython_language

    @staticmethod
    def return_preliminary(*args, **kwargs):
        pass

    @staticmethod
    def set_progress(*args, **kwargs):
        pass

    def push(self, pushable):
        if pushable != "code" and pushable not in self._inputs:
            msg = "'{}' is not pushable. Pushable inputs are: {}"
            raise NameError(msg.format(pushable, self._inputs + ["code"]))
        self._push_queue.put((pushable, self[pushable]))

    def transform(self):
        from ..core.cached_compile import exec_code
        code = self["code"]
        exec_code(
            code, identifier=self._name, 
            namespace=self, 
            inputs=self._inputs, 
            output=self._output_name,
            with_ipython_kernel=self._ipython_language
        )
        return self[self._output_name]

    def __getitem__(self, attr):
        try:
            return super().__getitem__(attr)
        except KeyError:
            if attr == "return_preliminary":
                return self.return_preliminary
            elif attr == "set_progress":
                return self.set_progress
            elif attr == "push":
                return self.push
            elif attr == "transform":
                return self.transform
            raise KeyError(attr) from None

    def _set_code(self, value):
        from ..core.cached_compile import analyze_code
        if callable(value):
            value = inspect.getsource(value)
        else:
            mode, _ = analyze_code(value, "transform")
            if mode == "function":
                value = textwrap.dedent(value)
                try:
                    exec(value, self)
                except Exception:
                    exc = traceback.format_exc()
                    self._push_queue.put((-1, exc))
        if value is not None:
            value = textwrap.dedent(value)

        super().__setitem__("code", value)

    def __setitem__(self, attr, value):
        if attr == "code":
            self._set_code(value)
        else:
            return super().__setitem__(attr, value)


class QueueStdStream:
    def __init__(self, queue, id):
        self._queue = queue
        self._id = id
    def isatty(self):
        return False
    def write(self, v):
        self._queue.put((self._id, v))
    def writelines(self, sequence):
        for s in sequence:
            self.write(s)
    def writeable(self):
        return True
    def flush(self):
        pass
    def readable(self):
        return False

def init_io_patched(self):
    """Redirect input streams and set a display hook."""
    from ipykernel.kernelapp import import_item
    # copy-paste: taken from ipykernel.kernelapp.IPKernelApp.init_io
    # Copyright (c) IPython Development Team.
    if self.outstream_class:
        outstream_factory = import_item(str(self.outstream_class))
        if sys.stdout is not None:
            sys.stdout.flush()

        e_stdout = None if self.quiet else sys.__stdout__
        e_stderr = None if self.quiet else sys.__stderr__

        sys.stdout = outstream_factory(self.session, self.iopub_thread,
                                        'stdout',
                                        echo=e_stdout)
        if sys.stderr is not None:
            sys.stderr.flush()
        sys.stderr = outstream_factory(self.session, self.iopub_thread,
                                        'stderr',
                                        echo=e_stderr)

    if self.displayhook_class:
        displayhook_factory = import_item(str(self.displayhook_class))
        self.displayhook = displayhook_factory(self.session, self.iopub_socket)
        sys.displayhook = self.displayhook

    self.patch_io()

def start_shell(
    name, connection_file, namespace, module_workspace, push_queue, inputs, 
    output_name, ipython_language
):
    from IPython import get_ipython
    from ..core.injector import transformer_injector
    from ipykernel.kernelapp import IPKernelApp
    ipshell = get_ipython()
    if ipshell is not None:
        ipshell.clear_instance()

    import asyncio
    asyncio.get_event_loop().stop()
    asyncio.set_event_loop(asyncio.new_event_loop())
    assert not asyncio.get_event_loop().is_running()

    sys.stdout = QueueStdStream(push_queue, -1)
    sys.stderr = QueueStdStream(push_queue, -2)

    app = IPKernelApp()

    # copy-paste: taken from ipykernel.kernelapp.IPKernelApp.initialize
    # Copyright (c) IPython Development Team.
    super(IPKernelApp, app).initialize([])

    app.connection_file = connection_file
    app.init_pdb()
    app.init_blackhole()
    app.init_connection_file()
    app.init_poller()
    app.init_sockets()
    app.init_heartbeat()
    # writing/displaying connection info must be *after* init_sockets/heartbeat
    app.write_connection_file()
    # Log connection info after writing connection file, so that the connection
    # file is definitely available at the time someone reads the log.
    ### app.log_connection_info()  # disable for Seamless  
    #app.init_io()
    init_io_patched(app)
    try:
        app.init_signal()
    except:
        # Catch exception when initializing signal fails, eg when running the
        # kernel on a separate thread
        if app.log_level < logging.CRITICAL:
            app.log.error("Unable to initialize signal:", exc_info=True)
    app.init_kernel()
    # shell init steps
    app.init_path()

    try:
        def stdout(msg):
           push_queue.put((-1, msg)) 
        def stderr(msg):
           push_queue.put((-2, msg)) 

        app.init_shell()
        # From now on, stdout and stderr are not working

        app.shell.banner1 = PYBANNER.format(
            name=name,
        )
        message = PYMESSAGE.format(
            name=name,
            CONSOLE_COMMAND=CONSOLE_COMMAND,
            connection_file=connection_file
        )
        stderr(message)
        app.init_gui_pylab()
        app.init_extensions()
        app.init_code()
        # flush stdout/stderr, so that anything written to these streams during
        # initialization do not get associated with the first execution request
        sys.stdout.flush()
        sys.stderr.flush()
        # /copy-paste

        with transformer_injector.active_workspace(module_workspace, namespace):
            shelldict = ShellDict(
                name, push_queue, inputs, 
                output_name=output_name, 
                ipython_language=ipython_language
            )
            shelldict.update(namespace)
            shelldict._set_code(shelldict["code"])

            app.kernel.user_ns = shelldict
            app.shell.set_completer_frame()    
            app.start()
    except Exception:
        exc = traceback.format_exc()
        stderr(exc)

class ShellHub:
    """One hub per transformer. There can be multiple shells per hub"""
    def __init__(self, name):
        self.name = name
        self.shells = {}
        self.shellnames = []
        self._destroyed = False

    def new_shell_name(self):
        if self.name not in self.shells:
            name = self.name
        else:
            ind = 1
            while 1:
                name = self.name + "-" + str(ind)
                if name not in self.shells:
                    break
        return name

    def new_shell(self, *args, **kwargs):
        raise NotImplementedError

    def _cleanup_shells(self):
        raise NotImplementedError

    def list_shells(self):
        raise NotImplementedError

    def destroy_shell(self, name):
        raise NotImplementedError

    def destroy(self):
        try:
            self._cleanup_shells()
            for name in list(self.shells.keys()):
                self.destroy_shell(name)
        finally:
            self._destroyed = True

class PyShellHub(ShellHub):
    def __init__(self, name, inputs, output_name, ipython_language, push_callback):
        super().__init__(name)
        #self.shells: name => (Process, connection_file) dict
        self.inputs = inputs
        self.output_name = output_name
        self.ipython_language = ipython_language
        self.push_callback = push_callback
        if multiprocessing.get_start_method(allow_none=True) is None:
            multiprocessing.set_start_method("fork")
        assert multiprocessing.get_start_method(allow_none=False) == "fork"
        self.push_queue = multiprocessing.Queue()        

    def new_shell(self, namespace, module_workspace):
        name = self.new_shell_name()
        connection_file = "seamless-shell-{}.json".format(name)
        args = (
            name, connection_file, namespace, module_workspace,
            self.push_queue, self.inputs, self.output_name,
            self.ipython_language
        )
        if multiprocessing.get_start_method(allow_none=True) is None:
            multiprocessing.set_start_method("fork")
        assert multiprocessing.get_start_method(allow_none=False) == "fork"
        process = Process(target=start_shell, args=args, daemon=True)
        self.shells[name] = process, connection_file
        self.shellnames.append(name)
        process.start()

    def _cleanup_shells(self):
        for name in list(self.shells.keys()):
            process, _ = self.shells[name]
            if not process.is_alive():
                self.shells.pop(name)
                self.shellnames.remove(name)

    def list_shells(self):
        self._cleanup_shells()
        if not len(self.shells):
            return
        result = "In a bash terminal, you can connect to the shell with:"
        if len(self.shellnames) > 1:
            result = """Multiple shells are available.
In a bash terminal, you can connect to each shell with:"""
        for name in self.shellnames:
            _, connection_file = self.shells[name]
            name2 = name + ": " if len(self.shellnames) > 1 else ""
            result += "\n{}{CONSOLE_COMMAND} {connection_file}".format(
                name2,
                CONSOLE_COMMAND=CONSOLE_COMMAND,
                connection_file=connection_file
            )
        return result

    async def listen_push_queue(self, interval):
        while not self._destroyed:
            try:
                pushable, value = self.push_queue.get_nowait()
                if pushable == -1:
                    sys.stdout.write(value)
                elif pushable == -2:
                    sys.stderr.write(value)
                else:
                    try:
                        self.push_callback(pushable, value)
                    except Exception:
                        traceback.print_exc()
            except Empty:
                await asyncio.sleep(interval)

    def destroy_shell(self, name):
        from ..core.transformation import forked_processes
        if name not in self.shells:
            raise KeyError(name)
        process, _ = self.shells.pop(name)            
        self.shellnames.remove(name)
        process.terminate()
        forked_processes[process] = time.time()

class BashShellHub(ShellHub):

        
    def new_shell(self, namespace, _):
        name = self.new_shell_name()
        docker_image = namespace.get("docker_image_", None)

        SEAMLESS_DEBUGGING_DIRECTORY = os.environ.get("SEAMLESS_DEBUGGING_DIRECTORY")
        if SEAMLESS_DEBUGGING_DIRECTORY is None:
            raise Exception("SEAMLESS_DEBUGGING_DIRECTORY undefined")
        shelldir = tempfile.mkdtemp(dir=SEAMLESS_DEBUGGING_DIRECTORY, prefix="shell-"+ name)

        pins_ = namespace["pins_"]
        if docker_image is None: # graphs/bash_transformer
            bashcode = namespace["bashcode"]
        else: # graphs/bash_transformer
            bashcode = namespace["docker_command"]
        PINS = namespace["PINS"]
        old_cwd = os.getcwd()
        env = OrderedDict()
        # from seamless/graphs/bash_transformer/executor.py
        try:
            os.chdir(shelldir)
            for pin in pins_:
                if pin == "pins_":
                    continue
                if docker_image is None:
                    if pin == "bashcode":
                        continue
                else:
                    if pin in ["docker_command", "docker_image_", "docker_options"]:
                        continue

                v = PINS[pin]
                if isinstance(v, Silk):
                    v = v.unsilk
                storage, form = get_form(v)
                if storage.startswith("mixed"):
                    raise TypeError("pin '%s' has '%s' data" % (pin, storage))
                if storage == "pure-plain":
                    if isinstance(form, str):
                        vv = str(v)
                        if not vv.endswith("\n"): vv += "\n"
                        if len(vv) <= 1000:
                            env[pin] = vv
                    else:
                        vv = json.dumps(v)
                    with open(pin, "w") as pinf:
                        pinf.write(vv)
                elif isinstance(v, bytes):
                    with open(pin, "bw") as pinf:
                        pinf.write(v)
                else:
                    if v.dtype == np.uint8 and v.ndim == 1:
                        vv = v.tobytes()
                        with open(pin, "bw") as pinf:
                            pinf.write(vv)
                    else:
                        with open(pin, "bw") as pinf:
                            np.save(pinf,v,allow_pickle=False)

            gen_env_code = ""
            for v in env:
                gen_env_code += "declare -p {}\n".format(v)
            try:
                gen_env_process = subprocess.run(
                    gen_env_code, capture_output=True, shell=True, check=True,
                    executable='/bin/bash',
                    env=env
                )
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr
                try:
                    stderr = stderr.decode()
                except:
                    pass
                print(stderr)
            gen_env_value = gen_env_process.stdout
            with open("ENVIRONMENT.sh", "wb") as f:
                f.write(gen_env_value)

            bashcode2 = """#!/bin/bash
set -u -e
"""
            bashcode2 += bashcode
            with open("transform.sh", "w") as f:
                f.write(bashcode2)
            os.chmod("transform.sh", 0o777)

        finally:
            os.chdir(old_cwd)

        if docker_image is None:
            bash_command = "cd {}".format(shelldir)
        else:
            bash_command = """docker run --rm -it \\
    -v {shelldir}:/run \\
    --workdir /run \\
    -u $(id -u ${{USER}}):$(id -g ${{USER}}) \\
    {docker_image} bash
  
If the Docker image "{docker_image}" requires root, eliminate the line starting with -u.
""".format(
            shelldir=shelldir,
            docker_image=docker_image
        )
        print(BASHMESSAGE.format(
            name=name,
            bash_command=bash_command
        ))

        self.shells[name] = shelldir, bash_command
        self.shellnames.append(name)


    def destroy_shell(self, name):
        if name not in self.shells:
            raise KeyError(name)
        shelldir, _ = self.shells.pop(name)            
        self.shellnames.remove(name)
        shutil.rmtree(shelldir, ignore_errors=True)

    def _cleanup_shells(self):
        pass

    def list_shells(self):
        if not len(self.shells):
            return
        result = "In a bash terminal, you can connect to the shell with:"
        if len(self.shellnames) > 1:
            result = """Multiple shells are available.
In a bash terminal, you can connect to each shell with:"""
        for name in self.shellnames:
            name2 = name + ": " if len(self.shellnames) > 1 else ""
            _, bash_command = self.shells[name]
            result += "\n" + name2 + bash_command
        return result


class ShellServer:
    def __init__(self):
        self.INTERVAL = 0.1
        self._shellhubs = {} #name-to-shellhub
        
    def _new_shellhub_name(self, name):
        if name not in self._shellhubs:
            return name
        else:
            ind = 1
            while 1:
                name2 = name + "-" + str(ind)
                if name2 not in self._shellhubs:
                    return name2

    def new_pyshellhub(self, name:str, inputs, output_name, ipython_language, push_callback):
        name = self._new_shellhub_name(name)
        shellhub = PyShellHub(name, inputs, output_name, ipython_language, push_callback)
        self._shellhubs[name] = shellhub
        asyncio.ensure_future(shellhub.listen_push_queue(self.INTERVAL))
        return name

    def new_bashshellhub(self, name:str):
        name = self._new_shellhub_name(name)
        shellhub = BashShellHub(name)
        self._shellhubs[name] = shellhub
        return name

    def new_shell_from_namespace(self, name:str, namespace, module_workspace):
        if name not in self._shellhubs:
            raise KeyError(name)
        return self._shellhubs[name].new_shell(namespace, module_workspace)

    async def new_shell_from_transformation(self, name:str, transformation):
        from ..core.cache.transformation_cache import transformation_cache
        from ..core.transformation import build_transformation_namespace
        from ..core.build_module import build_all_modules
        from ..compiler import compilers as default_compilers, languages as default_languages
        if name not in self._shellhubs:
            raise KeyError(name)
        semantic_cache = transformation_cache.build_semantic_cache(transformation)
        tf_ns = await build_transformation_namespace(
            transformation, 
            semantic_cache,
            name
        )
        code, namespace, modules_to_build = tf_ns
        namespace["code"] = code
        compilers = transformation.get("__compilers__", default_compilers)
        languages = transformation.get("__languages__", default_languages)            
        module_workspace = {}
        build_all_modules(
            modules_to_build, module_workspace,
            compilers=compilers, languages=languages,
            module_debug_mounts=None
        )
        return self.new_shell_from_namespace(name, namespace, module_workspace)

    def list_shells(self, name:str):
        if name not in self._shellhubs:
            raise KeyError(name)
        return self._shellhubs[name].list_shells()

    def destroy_shell(self, name, shellname=None):
        if name not in self._shellhubs:
            raise KeyError(name)
        shellhub = self._shellhubs[name]
        if shellname is None:
            shellnames = shellhub.shellnames
            if len(shellnames) > 1:
                raise Exception("Multiple shells exist")
            shellname = shellnames[0]
        shellhub.destroy_cell(shellname)        

    def destroy_shellhub(self, name):
        if name not in self._shellhubs:
            raise KeyError(name)
        shellhub = self._shellhubs.pop(name)
        shellhub.destroy()

    def destroy(self):
        while len(self._shellhubs):
            name = list(self._shellhubs.keys())[0]
            self.destroy_shellhub(name)
       
shellserver = ShellServer()
import atexit

atexit.register(shellserver.destroy)
