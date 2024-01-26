#!/bin/bash
set -u -e
rm -rf ./fairdir ./bufferdir
mkdir ./fairdir ./bufferdir
seamless-fairdir-build ./fairdir testset.yaml --source ./testset --bufferdir ./bufferdir --verbose
seamless-fairdir-add-distribution ./fairdir mydataset mydataset --version 1 
checksum=$(python -c 'import json; print(json.load(open("./fairdir/distributions/mydataset.json"))[0]["checksum"])')
echo checksum=$checksum
seamless-bufferdir-deploy-deepfolder $checksum ./bufferdir
export FAIRSERVER_DIR=./fairdir
python $SEAMLESS_TOOLS_DIR/tools/fairserver/fairserver.py &
sleep 2
trap 'kill -1 $(jobs -p); kill $(jobs -p); kill -9 $(jobs -p)' EXIT
unset SEAMLESS_READ_BUFFER_SERVER
export SEAMLESS_READ_BUFFER_FOLDERS=./bufferdir
export FAIRSERVER=http://localhost:61918
python run.py
rm -rf fairdir bufferdir