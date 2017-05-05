import os, subprocess, tempfile, shlex, glob
result = None
d = None

def format_msg(message, headline):
    msg = "Line {0}:\n    {1}\n{2}:\n{3}"\
      .format(PARAMS["lineno"], PARAMS["source"], headline, message)
    return msg

try:
    d = tempfile.mkdtemp(dir="/dev/shm")
    command_params = []
    created_files = []
    for ref in PARAMS["refs"]:
        if isinstance(ref, str):
            value = globals()[ref]
            inp_type = PARAMS["inputs"][ref]
            if inp_type == "variable":
                command_params.append(shlex.quote(value))
            elif inp_type == "doc":
                filename = d + "/doc_" + ref
                open(filename, "w").write(value)
                created_files.append(filename)
                command_params.append(filename)
            else:
                raise TypeError(inp_type)
        else:
            typ, value = ref["type"], ref["value"]
            if typ == "env":
                command_params.append(value)
            elif typ == "file":
                if value is None:
                    filename = "/dev/null"
                else:
                    value = os.path.expanduser(value)
                    filename = os.path.abspath(value)
                command_params.append(filename)
            elif typ == "varexp":
                refs = ref["refs"]
                ref_values = [globals()[r] for r in refs]
                value = value.format(*ref_values)
                command_params.append(shlex.quote(value))
            else:
                raise TypeError(typ)
    command = [param.format(*command_params) \
                for param in PARAMS["command"]]
    stdout = None
    stderr = subprocess.PIPE
    capture = False
    return_mode = []
    print_stdout = True
    print_stderr = True
    for output in PARAMS["output_refs"]:
        if output["type"] == "stdout":
            stdout = subprocess.PIPE
            print_stdout = False
            if output["name"] is not None:
                return_mode.append("stdout")
        elif output["type"] == "stderr":
            stderr = subprocess.PIPE
            print_stderr = False
            if output["name"] is not None:
                return_mode.append("stderr")
        elif output["type"] == "stdout+stderr":
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
            print_stdout = False
            print_stderr = False
            if output["name"] is not None:
                return_mode.append("stdout")
        elif output["type"] == "capture":
            capture = True
            return_mode.append("capture")
        else:
            raise TypeError(output["type"])
    command = "cd %s;" % d + " ".join(command)
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr, shell=True)
    stdout_data, stderr_data = process.communicate()
    if stdout_data is not None:
        stdout_data = stdout_data.decode("utf-8")
    if stderr_data is not None:
        stderr_data = stderr_data.decode("utf-8")
    if process.returncode:
        message = "Process exited with return code %d\n" % process.returncode
        message += "Standard error:\n%s" % stderr_data
        msg = format_msg(message, "Error message")
        raise Exception(msg)
    else:
        if print_stdout and len(stdout_data):
            print(format_msg(stdout_data, "Standard output"))
        if print_stderr and len(stderr_data):
            print(format_msg(stderr_data, "Standard error"))
    if capture:
        new_files = []
        for dirpath, dirnames, filenames in os.walk(d):
            for filename in filenames:
                new_file = os.path.join(dirpath, filename)
                if new_file not in created_files:
                    new_files.append(new_file)
        capture_data = {}
        for f in new_files:
            ff = f[len(d+"/"):]
            capture_data[ff] = open(f).read()

    assert len(return_mode) <= 1, return_mode #TODO: stdout and stderr to different targets => return JSON
    return_mode = return_mode[0] #TODO, see above
    if return_mode == "stdout":
        result = stdout_data
    elif return_mode == "stderr":
        result = stderr_data
    elif return_mode == "capture":
        result = capture_data
finally:
    if d is not None:
        os.system("rm -rf %s" % d)
print("RUN", PARAMS["source"])
return result
