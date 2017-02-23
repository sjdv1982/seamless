hive1 = """
import hive
def build_hive(i, ex, cls):
    ex.v_a = hive.attribute("int", 80)
    i.p_a = hive.push_in(ex.v_a)
    ex.a = hive.antenna(i.p_a)
MyHive = hive.hive("MyHive", build_hive)
"""

hive2 = """
import hive
def build_hive(i, ex, cls):
    ex.v_b = hive.attribute("float", 1.0)
    i.p_b = hive.push_in(ex.v_b)
    ex.b = hive.antenna(i.p_b)
    ex.v_c = hive.attribute("int", 2)
    i.p_c = hive.push_in(ex.v_c)
    ex.c = hive.antenna(i.p_c)
MyHive = hive.hive("MyHive", build_hive)
"""

hive3 = """
import hive
def build_hive(i, ex, cls):

    ex.v_result = hive.attribute("int")
    i.p_result = hive.push_out(ex.v_result)

    def add(self):
        print("adding {0} and {1}".format(self.v_x, self.v_y))
        self.v_result = self.v_x + self.v_y
        self.result.push()
    i.add = hive.modifier(add)

    ex.v_x = hive.attribute("float", 1.0)
    ex.v_y = hive.attribute("int", 2)

    i.p_x = hive.push_in(ex.v_x)
    i.p_y = hive.push_in(ex.v_y)
    ex.x = hive.antenna(i.p_x)
    ex.y = hive.antenna(i.p_y)

    ex.result = hive.output(i.p_result)
    hive.trigger(i.p_x, i.add)
    hive.trigger(i.p_y, i.add)

MyHive = hive.hive("MyHive", build_hive)
#def func(x):
#    print("RESULT", x)
#myhive = MyHive()
#hive.connect(myhive.result, hive.push_in(func))

"""

from seamless import context, cell
from seamless.lib.hive.hiveprocess import hiveprocess

ctx = context()
ctx.my_hive = cell(("text", "code", "python"))
ctx.my_hive.set(hive1)
ctx.registrar.hive.register(ctx.my_hive)

#myhive = ctx.registrar.hive.get("MyHive")()

hp = ctx.hp = hiveprocess("MyHive")
ed = ctx.hp.ed

print(ed.a)
print(hp.a)

ctx.my_hive.set(hive2)
import time; time.sleep(0.001)
print(ed.b)
print(hp.b)

ctx.my_hive.set(hive3)
ctx.x = hp.x.cell()
ctx.y = hp.y.cell()
ctx.result = hp.result.cell()
ctx.x.set(2)
ctx.y.set(4)
import time; time.sleep(0.01)
print(ctx.result.data)
