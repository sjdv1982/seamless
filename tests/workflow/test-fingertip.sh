#!/bin/bash

echo 'Part 1'
python3 test-fingertip1.py
echo ''

echo 'Part 2'
python3 test-fingertip2.py
echo ''

echo 'Part 3'
python3 test-fingertip1.py
echo ''

export SEAMLESS_READ_BUFFER_SERVERS=""
export SEAMLESS_WRITE_BUFFER_SERVER=""
echo 'Part 4'
python3 test-fingertip1.py
echo ''

echo 'Part 5'
python3 test-fingertip2.py
echo ''