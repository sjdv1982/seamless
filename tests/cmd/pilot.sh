#!/bin/bash
echo Run 1
time seamless --local -mx --input pilot -c './pilot-inner.sh'
echo
echo Run 2a
time seamless --local -mx --input pilot -c './pilot-inner.sh'
echo
echo Run 2b
cat pilot-inner.sh > pilot-inner2.sh
time seamless --local -mx --input pilot -c './pilot-inner2.sh'
echo ' ' >> pilot-inner2.sh
echo 'echo OK' >> pilot-inner2.sh
echo
echo Run 3
cat pilot-inner.sh > pilot-inner2.sh
echo ' ' >> pilot-inner2.sh
echo 'echo OK' >> pilot-inner2.sh
time seamless --local -mx --input pilot -c './pilot-inner2.sh'
rm -f pilot-inner2.sh