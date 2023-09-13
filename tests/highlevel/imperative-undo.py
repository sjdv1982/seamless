import seamless
seamless.config.delegate(level=3)

from seamless import transformer

@transformer(return_transformation=True)
def add(a, b):
    return a + b

t1 = add(2, 3)
t1.compute()
five = t1.checksum

t2 = add(2, 2)
t2.compute()
print(f"2 + 2 = {t2.value}")

t2cs = t2.as_checksum()
t2.undo()

from seamless.config import database
database.set_transformation_result(t2cs.bytes(), five.bytes())

t2.compute()
print(f"2 + 2 = {t2.value}")

t2 = add(2, 2)
t2.compute()
print(f"2 + 2 = {t2.value}")

t2.undo()