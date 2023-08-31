#!/bin/bash

code='''
print("START")
import traceback
import sys
from seamless.imperative import transformer

if not sys.warnoptions:
    import warnings
    warnings.simplefilter("ignore")

@transformer
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b

try:
    print(func(12, 13))
except RuntimeError:
    traceback.print_exc()

'''

echo 'Locally executed code'
echo ''

echo "$code" > imperative-jupyter-TEMP.py

echo 'Python'
python imperative-jupyter-TEMP.py
echo ''

echo 'Jupyter'
jupyter console <<EOF |& awk '/START/{p=1}p==1'
%run imperative-jupyter-TEMP.py
exit()
EOF
echo ''

echo 'Delegated code'
echo ''

code2='import seamless
seamless.config.block()
seamless.config.init_from_env()
'$code

echo "$code2" > imperative-jupyter-TEMP.py

echo 'Python'
python imperative-jupyter-TEMP.py
echo ''

echo 'Jupyter'
jupyter console <<EOF |& awk '/START/{p=1}p==1'
%run imperative-jupyter-TEMP.py
exit()
EOF
echo ''

rm -f imperative-jupyter-TEMP.py