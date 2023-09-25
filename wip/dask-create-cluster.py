import sys
import dask
dask.config.set({'distributed.worker.multiprocessing-method': 'fork'})
dask.config.set({'distributed.worker.daemon': False})

from dask.distributed import LocalCluster
cluster = LocalCluster()

print(cluster.scheduler_address)
sys.stdout.flush()

import time
time.sleep(9999999)