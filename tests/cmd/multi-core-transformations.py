import sys
    
def func(jobid, sleep, rand):
    print("Run job", jobid, file=sys.stderr)
    import time
    time.sleep(sleep)
    return jobid

jobid = int(sys.argv[1])
sleep = float(sys.argv[2])
rand = float(sys.argv[3])

print(func(jobid, sleep, rand))
