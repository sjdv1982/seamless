import sys
import dask

from dask.distributed import Client
from dask.distributed import WorkerPlugin


class SeamlessWorkerPlugin(WorkerPlugin):
    def setup(self, worker):
        try:
            import seamless
            from seamless.workflow.core.transformation import (
                get_global_info,
                execution_metadata0,
            )
            from seamless.workflow.core.cache.transformation_cache import (
                transformation_cache,
            )
            from seamless.util import set_unforked_process
        except ImportError:
            raise RuntimeError(
                "Seamless must be installed on your Dask cluster"
            ) from None

        set_unforked_process()
        seamless.config.set_ncores(4)
        seamless.delegate(level=3)
        transformation_cache.stateless = True
        get_global_info()
        execution_metadata0["Executor"] = "dask-test-worker"
        print("Seamless worker is up!", worker)


import seamless
from seamless.config import InProcessAssistant


class PocketDaskAssistant(InProcessAssistant):
    def __init__(self, client: Client):
        self.client = client

    async def run_job(self, checksum, tf_dunder):
        import asyncio

        # in this test, assume that every job is submitted only once
        try:

            def run_transformation(checksum, tf_dunder):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return seamless.run_transformation(
                    checksum, fingertip=True, tf_dunder=tf_dunder
                )

            result = self.client.submit(
                run_transformation, checksum, tf_dunder=tf_dunder
            )
            if isinstance(result, dask.distributed.Future):
                result = result.result()
            return result

        except Exception:
            import traceback

            traceback.print_exc()


scheduler_address = sys.argv[1]
offset = float(sys.argv[2])

client = Client(scheduler_address)
client.register_plugin(SeamlessWorkerPlugin())
seamless.delegate(level=3)  # to make sure that delegation has been set up
seamless.config.set_inprocess_assistant(PocketDaskAssistant(client))
seamless.config.block_local()
import time

start = time.time()
print("START")

from seamless import transformer


@transformer
def addf(a, b, offset):
    import time

    time.sleep(0.5)
    return a + b + offset


print(addf(4, 5, offset))
print("{:.1f} seconds elapsed".format(time.time() - start))
print(addf(10, 12, offset))
print("{:.1f} seconds elapsed".format(time.time() - start))
print(addf(100, 200, offset))
print("{:.1f} seconds elapsed".format(time.time() - start))
