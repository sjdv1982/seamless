#!/bin/bash
set -u -e
export ntrials=${1:-1000}
seeds=$(python -c '
import sys
import numpy as np
np.random.seed(0)
ntrials = int(sys.argv[1])
seeds = np.random.randint(0, 999999, ntrials)
print(" ".join([str(seed) for seed in seeds]))
' $ntrials
)
seeds=($seeds)
rm -f calc_pi.job-* manyjobs-multi.jobfile .seamless-queue
seamless-queue &   # start working immediately. You can use -q to get better timings
for i in $(seq $ntrials); do
    i2=$((i-1))
    export seed="${seeds[$i2]}"
    cmd="python3 calc_pi.py --seed $seed --ndots 1000000000 > calc_pi.job-$i"
    echo $cmd >> manyjobs-multi.jobfile
    echo >> manyjobs-multi.jobfile
    echo >> manyjobs-multi.jobfile
done

trap 'kill -1 $(jobs -p); kill $(jobs -p); kill -9 $(jobs -p)' EXIT

# You can use -q to get better timings, or -v/-vv to get better progress
seamless-multi --fingertip --ncores 2 manyjobs-multi.jobfile  

echo 'Jobs submitted'
seamless-queue-finish

python3 -c '
import sys
import numpy as np
ntrials = int(sys.argv[1])
results = []
for n in range(ntrials):
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
print(results.mean(), results.std(), np.pi)    
' $ntrials

rm -f manyjobs-multi.jobfile