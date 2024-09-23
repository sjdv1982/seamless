import sys
import time

time.sleep(2)
a = int(open(sys.argv[1]).read())
b = int(open(sys.argv[2]).read())
print(a + b)
