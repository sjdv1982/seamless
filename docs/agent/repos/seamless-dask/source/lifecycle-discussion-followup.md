# Seamless Dask lifecycle discussion

Notes distilled from the review of `lifecycle.txt`, the current transformer code, and the follow-up Q&A.

## Seven-point review (status)

- **1. Keys lack resource**: Dask keys must include `resource` to avoid cross-resource deduping/cancellation. Scratch/meta can stay out given Seamless guarantees. _Status: needs key change for resource._
- **2. Base returning before durability**: Acceptable if Seamless guarantees checksum ⇒ retrievable buffer (scratch deduped included) and the “hit” path waits/flushes appropriately. _Status: OK under that guarantee._
- **3. Dummy fat alias**: Replace the dummy alias with submitting the real fat task under `K2` on the base worker (`worker_client(secede=True)`), returning the concrete result, only if `K2` isn’t known. _Status: covered by this pattern._
- **4. Late alias/race**: Checking “only if `K2` not present” leaves a narrow race; eliminating it would require avoiding the provisional key. _Status: accepted race (or avoid provisional key)._
- **5. Short TTL cancels work**: A ~10s strong-cache TTL can drop in-flight futures if no strong refs remain. Need longer pinning/refresh until completion for tasks you care about. _Status: open. To be addressed using Dask eagerness_
- **6. Locality best-effort**: Dask P2P copies are fine; “hot buffer on base worker” is best-effort unless you pin placement. _Status: accepted._
- **7. Cache hit but missing buffer**: If checksum always implies a retrievable buffer (scratch included) and “hit” paths ensure availability before returning, concern is satisfied. _Status: OK under that guarantee._

## Dask eagerness

- `Client.submit` is eager: once deps are ready, tasks run as soon as capacity is available, even if the client never calls `.result()` and no downstreams exist.
- To keep the fat task idle until needed: either submit it only when a consumer shows up. Priority alone doesn’t make it lazy.

## Misc notes

- If fat is submitted up front and runs longer than the TTL, it can be canceled once the client stops pinning it; extend/pin if you want it to finish for late downstreams.
- Buffer serialization: `Buffer` is pickled as plain Python (bytes + checksum). For zero-copy frames, add custom `dask_serialize`/`dask_deserialize` or ship raw bytes/checksum and rehydrate.
