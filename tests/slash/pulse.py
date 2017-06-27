from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE,SIG_DFL) #ignore pipe errors

import time
import sys
pulses = int(sys.argv[1])
delay = float(sys.argv[2])
for n in range(pulses):
    time.sleep(delay)
    print(n+1)
    print("PULSE", n+1,file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
