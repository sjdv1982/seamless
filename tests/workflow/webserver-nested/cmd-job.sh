#!/bin/bash
set -u -e
seeds=$(python -c '
import sys
import numpy as np
seeds = np.load("seeds.npy")
print(" ".join([str(seed) for seed in seeds]))
')
seeds=($seeds)
nseeds=${#seeds[@]}
for i in $(seq $nseeds); do
    i2=$((i-1))
    seed="${seeds[$i2]}"
    cmd="python3 calc_pi.py --seed $seed --ndots $ndots > calc_pi.job-$i"
    seamless -c "$cmd" &
    sleep 0.2  # bin/seamless needs 0.5-1s to start up, at full CPU, accessing hard disk
    while [ $(jobs -r | wc -l) -gt 300 ]; do  # limiting factor is memory (~50 MB per process)
        echo WAIT... $i
        wait -n
    done
done
wait

python3 -c '
import sys
import numpy as np
nseeds = int(sys.argv[1])
results = []
for n in range(nseeds):
    fname = f"calc_pi.job-{n+1}"
    with open(fname) as f:
        data = f.read()
    try:
        curr_pi = float(data)
    except ValueError:
        print("Error for job {}".format(n+1))
        exit(1)
    results.append(curr_pi)

results = np.array(results)
print(results.mean())    
' $nseeds > RESULT