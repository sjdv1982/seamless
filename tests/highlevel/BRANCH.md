Branch to implement imperative DAG-less mode 
(https://github.com/sjdv1982/seamless/issues/130 and https://github.com/sjdv1982/seamless/issues/190)

First, simple "imperative" draft code that can run a transformation w/o database.

DONE
Also for Jupyter, transformer-inside-transformer, and transformer-inside-transformer-inside-transformer
The latter is now supported by injecting the 'transformer' object directly

******************
Lots of stuff works now
TODO: error message for running @transformer at top level with jobless:
1. Tell user to use local=True
2. Tell user to run with @transformer_async
3. Tell user to put inside transformer
Test all three
******************