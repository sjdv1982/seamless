import time
import loky
import concurrent 

executor = loky.get_reusable_executor()
#executor = concurrent.futures.ThreadPoolExecutor()
def func():
    import sys
    time.sleep(100)
    print("run exit")
    sys.exit(0)

fut = executor.submit(func)
try:
    r = fut.exception()
    print("EXC", r)
except:
    print("exception caught")
print("Main process still alive")
time.sleep(3)