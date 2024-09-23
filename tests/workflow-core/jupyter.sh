#!/bin/bash

code='''import traceback
print("START")
import seamless
seamless.delegate(False)
from seamless.workflow.core import context
ctx = context(toplevel=True)

try:
    ctx.compute()
except RuntimeError:
    traceback.print_exc(0)
'''

f=`mktemp`
echo "$code" > $f

jupyter console <<EOF |& awk '/START/{p=1}p==1'
%run $f
exit()
EOF

rm -f $f