import glob
from re import S
from requests import ConnectionError

import seamless
from seamless.highlevel.Cell import FolderCell
try:
    seamless.database_cache.connect()
    seamless.database_sink.connect()
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
print(ctx.folder_sub.checksum)
print(ctx.tf._get_htf()["pins"])
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)

#ctx.tf.language = "bash"

