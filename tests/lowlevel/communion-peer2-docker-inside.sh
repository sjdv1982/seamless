#!/bin/bash
bridge=172.17.0.1
export SEAMLESS_COMMUNION_ID=Peer2
port=$(docker port Peer1 | grep 8601 | sed 's/:/ /' | awk '{print $4}')
export SEAMLESS_COMMUNION_INCOMING=$bridge:$port

seamlessdir=`python3 -c 'import seamless,os;print(os.path.dirname(seamless.__file__))'`/../
docker run \
    --rm \
    -it \
    --name $SEAMLESS_COMMUNION_ID \
    -e SEAMLESS_COMMUNION_ID=$SEAMLESS_COMMUNION_ID \
    -e SEAMLESS_COMMUNION_INCOMING=$SEAMLESS_COMMUNION_INCOMING \
    -P \
    -v `pwd`:/cwd \
    -v $seamlessdir:/seamless \
    -e "PYTHONPATH=/seamless" \
    --workdir /cwd \
    -u jovyan \
    seamless-devel python3 communion-peer2.py
