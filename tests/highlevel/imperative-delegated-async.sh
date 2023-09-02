#!/bin/bash

jupyter console <<EOF |& awk '/START/{p=1}p==1'
%load imperative-delegated-async.py

exit()
EOF
