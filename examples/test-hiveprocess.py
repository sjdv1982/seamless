hive1 = """
import hive
def build_hive(i, ex, cls):
    ex.a = hive.attribute("int", 80)
MyHive = hive.hive("MyHive", build_hive)
"""

hive2 = """
import hive
def build_hive(i, ex, cls):
    ex.b = hive.attribute("float", 1.0)
    ex.c = hive.attribute("int", 2)
MyHive = hive.hive("MyHive", build_hive)
"""


from seamless import context, cell
from seamless.lib.hive.hiveprocess import hiveprocess

ctx = context()
ctx.my_hive = cell(("text", "code", "python"))
ctx.my_hive.set(hive1)
ctx.registrar.hive.register(ctx.my_hive)

#myhive = ctx.registrar.hive.get("MyHive")()

hp = hiveprocess("MyHive")
print(hp.ed.a)

ctx.my_hive.set(hive2)
import time; time.sleep(0.001)
print(hp.ed.b)
