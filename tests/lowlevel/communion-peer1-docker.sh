#!/bin/bash
export SEAMLESS_COMMUNION_ID=Peer1
export SEAMLESS_COMMUNION_OUTGOING=8601
export SEAMLESS_COMMUNION_OUTGOING_ADDRESS=0.0.0.0

seamlessdir=`python3 -c 'import seamless,os;print(os.path.dirname(seamless.__file__))'`/../
docker run \
    --rm \
    -it \
    --name $SEAMLESS_COMMUNION_ID \
    --expose $SEAMLESS_COMMUNION_OUTGOING \
    -e SEAMLESS_COMMUNION_ID=$SEAMLESS_COMMUNION_ID \
    -e SEAMLESS_COMMUNION_OUTGOING=$SEAMLESS_COMMUNION_OUTGOING \
    -e SEAMLESS_COMMUNION_OUTGOING_ADDRESS=$SEAMLESS_COMMUNION_OUTGOING_ADDRESS \
    -P \
    -v `pwd`:/cwd \
    -v $seamlessdir:/seamless \
    -e "PYTHONPATH=/seamless" \
    --workdir /cwd \
    -u jovyan \
    seamless-devel ipython3 -i communion-peer1.py -- --interactive