import seamless
seamless.database_cache.connect()
seamless.database_sink.connect()

from seamless.imperative import transformer

@transformer
def func2(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(7)
        return 100 * a + b
    func.blocking = False

    v1 = func(a, b)
    v2 = func(b, a)
    v3 = func(2 * a, 2 * b)
    return v1.value + v2.value + v3.value

import time
t = time.time()
print("Wait for ~8 seconds..")
result = func2(1,2)
print(result)
print("Time: {:.1f} seconds".format(time.time() - t))
