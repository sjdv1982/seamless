"""
Serves buffers from a dummy buffer directory (./bufferserver/bufferdir)
In real life, you will probably want:
- to expose the ./buffers/ directory of a Seamless database 
or:
- to expose a vault

Seamless reads the SEAMLESS_BUFFER_SERVERS environmental variable
 as comma-separated strings.
Buffer servers are a very-last-resort option to prevent a buffer cache miss,
 and SEAMLESS_BUFFER_SERVERS is re-read every time it is needed
"""

import atexit, os
PORT=7654

from seamless.core import context, cell

docker_cmd = """docker run --name mynginx2 \
    --mount type=bind,source={bufferdir},target=/usr/share/nginx/html,readonly \
    --mount type=bind,source={conf},target=/etc/nginx/conf,readonly \
    -p {port}:80 -d nginx > /dev/null
"""
def kill_docker():
    os.system("docker stop mynginx2")
    os.system("docker rm mynginx2")
atexit.register(kill_docker)

currdir = os.path.abspath(os.path.split(__file__)[0])
if currdir.startswith("/cwd"):
    currdir = os.environ["HOSTCWD"] + currdir[4:]
os.system(docker_cmd.format(
    bufferdir=currdir+"/bufferserver/bufferdir",
    conf=currdir+"/bufferserver/conf",
    port=PORT,
))

import time
time.sleep(1)
os.system("curl -s localhost:{port}/78aeb2071cba3943ebfc2a8a39216301d85107b2db2075169a31f82a362d0e4d".format(port=PORT))
os.environ["SEAMLESS_BUFFER_SERVERS"] = "http://localhost:{port}".format(port=PORT)

ctx = context(toplevel=True)
ctx.c1 = cell("int").set_checksum("6132e913fd0ae2c9aeacc8d99a02880df196fbab2ef62dbb62a6a4ae6d3f5fdd")
ctx.c2 = cell("float").set_checksum("b71810195f83561dae62b15cded985cf412f47078ed126b02fa9a83ef7c7b7dc")
ctx.c3 = cell("plain").set_checksum("78aeb2071cba3943ebfc2a8a39216301d85107b2db2075169a31f82a362d0e4d")
ctx.c4 = cell("plain").set_checksum("e04b521c60ab8442aa626aa573c32052c81346899443c2b9d10bae997dc08123")
ctx.compute()
print(ctx.c1.checksum)
print(ctx.c1.value)
print(ctx.c2.value)
print(ctx.c3.value)
print(ctx.c4.value)