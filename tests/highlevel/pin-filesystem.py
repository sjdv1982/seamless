import glob
from re import S
from requests import ConnectionError

import subprocess
docker_file = """FROM ubuntu:latest
RUN apt update && apt -y install openssl   
"""
subprocess.run("docker build -t openssl -", shell=True,input=docker_file.encode())

import seamless
from seamless.highlevel.Cell import FolderCell
try:
    seamless.database_cache.connect()
    print("Database found")
except ConnectionError:
    print("Database not found")

from seamless.highlevel import Context, DeepFolderCell, Transformer

def end():
    print(deepfolder_checksum)  

deepfolder_checksum = glob.glob("/tmp/PIN-FILESYSTEM-TEST-DB/shared-directories/*")[0].split("/")[-1]
import atexit
atexit.register(end)

ctx = Context()
ctx.deepfolder = DeepFolderCell()
ctx.deepfolder.set_checksum(deepfolder_checksum)
ctx.compute()
print(ctx.deepfolder.data)
print(ctx.deepfolder.exception)
print(ctx.deepfolder.checksum)
print()
ctx.tf = Transformer()
def code(**kwargs):
    print(PINS.keys())
    for pin in sorted(FILESYSTEM.keys()):
        print(pin)
        print(FILESYSTEM[pin])
        print(PINS[pin])
        print()
    return 42
ctx.tf.deepfolderpin = ctx.deepfolder
ctx.tf.code = code
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
print()

print("Stage 2")
ctx.deepfolder_sub = DeepFolderCell()
ctx.deepfolder_sub = ctx.deepfolder
ctx.tf.folder_sub_pin = ctx.deepfolder_sub
ctx.translate()
ctx.deepfolder_sub.whitelist = ["sub/test2.txt", "sub/test3.npy"]
ctx.compute()
print(ctx.tf._get_htf()["pins"])
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
print()
print(ctx.deepfolder_sub.checksum)
print(ctx.deepfolder_sub.filtered_checksum, ctx.deepfolder_sub.filtered_keyorder)
print(ctx.deepfolder_sub.whitelist)
print()

print("Stage 3")
ctx.folder_sub = FolderCell()
ctx.folder_sub = ctx.deepfolder_sub
ctx.tf.folder_sub_pin = ctx.folder_sub
ctx.compute()
v = ctx.folder_sub.value.unsilk
print(v.keys() if v is not None else None)
print(v)
print(ctx.folder_sub.checksum)
print(ctx.tf._get_htf()["pins"])
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
print()

print("Stage 4")
ctx.tf.language = "bash"
ctx.tf.code = """
echo LS
ls
touch a
cat a
echo
echo DEEPFOLDERPIN ${deepfolderpin}
echo FOLDER_SUB_PIN ${folder_sub_pin}
function list() {
    dirname=$1
    find -L $dirname -name '*' -type f -print -exec openssl dgst -sha3-256 {} \; | awk '{x=$1;getline}{print x,$2}' | sort -k1 
    echo ''
}
list deepfolderpin
list folder_sub_pin
list ${deepfolderpin}
touch RESULT
"""
ctx.tf.environment.set_which(["openssl"], format="plain")
ctx.compute()
v = ctx.folder_sub.value.unsilk
print(v.keys() if v is not None else None)
print(ctx.folder_sub.checksum)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)

print("Stage 4a")
ctx.tf.a = "TESTSTRING"
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
del ctx.tf.pins.a

print("Stage 5")
ctx.tf.docker_image = "openssl"
ctx.tf.environment.set_which(None, "plain")
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)

print("Stage 5a")
ctx.tf.a = "TESTSTRING"
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
