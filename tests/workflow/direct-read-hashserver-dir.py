from seamless import Checksum, CacheMissError
import seamless

seamless.delegate(1)
try:
    print(Checksum.load("dummy-directory/1234.txt").resolve("str"))
except CacheMissError:
    print("Cache miss")
