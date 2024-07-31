import seamless
seamless.delegate(False)

from seamless import transformer

@transformer
def func(a, b):
    return a + b

result = func(88, 17)
print(result, type(result))
print(func.celltypes)
print(func.celltypes.a)
print(func.celltypes.b)
func.celltypes.a = "str"
func.celltypes.b = "str"
print(func.celltypes)
print(func.celltypes.a)
print(func.celltypes.b)
result = func(88, 17)
print(result, type(result))
func.celltypes.result = "bytes"
print(func.celltypes)
print(func.celltypes.result)
result = func(88, 17)
print(result, type(result))
