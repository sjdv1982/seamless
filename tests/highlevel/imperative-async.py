print("START")

from seamless import transformer

@transformer(return_transformation=True)
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b

result = await func(88, 17).task() # takes 0.5 sec
print(result)
result = await func(88, 17).task() # immediate
print(result)
result = await func(21, 17).task() # immediate
print(result)