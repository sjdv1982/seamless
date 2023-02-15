Branch to implement imperative DAG-less mode 
(https://github.com/sjdv1982/seamless/issues/130 and https://github.com/sjdv1982/seamless/issues/190)

First, simple "imperative" draft code that can run a transformation w/o database.

DONE
Also for Jupyter, transformer-inside-transformer, and transformer-inside-transformer-inside-transformer
The latter is now supported by injecting the 'transformer' object directly

******************
Lots of stuff works now, including top-level @transformer
Probably nothing left to do, except API documentation/rewrite

However, non-blocking evaluation (not asyncio, more like JAX) would be nice
******************

NOTE: Deadlock is possible if a nested local transformer reserves more cores than available!