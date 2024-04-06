#!/bin/bash
set -u
ASSISTANT=$1
rm -rf dummy-directory dummy-bufferfolder dummy-database
mkdir dummy-directory dummy-bufferfolder dummy-database
export SEAMLESS_HASHSERVER_DIRECTORY=$(pwd)/dummy-bufferfolder
export SEAMLESS_DATABASE_DIRECTORY=$(pwd)/dummy-database
seamless-delegate-stop 1>&2
seamless-delegate $ASSISTANT 1>&2

cd dummy-directory
seamless -c 'echo Random text > random.txt'
cs=11cd2207ae82a0ff9d4f90c6f469809444e32351cf38f227086d615e049b76b3
echo 1
cat random.txt
rm -rf random.txt
seamless-download -c $cs
cat $cs
echo ''
seamless-delete-buffer ../dummy-bufferfolder/ random.txt.CHECKSUM 2>&1
echo 2
seamless-fingertip $cs
echo ''
seamless-delete-buffer ../dummy-bufferfolder/ 7f98512bbdcef980352d117e2d2df55546bcb37648999b0f794331fcf276059a 2>&1
echo 3
seamless-fingertip $cs

cd ..
rm -rf dummy-directory dummy-bufferfolder dummy-database
seamless-delegate-stop 1>&2
