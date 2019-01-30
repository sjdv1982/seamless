#!/bin/bash
export SEAMLESS_COMMUNION_ID=Peer1
export SEAMLESS_COMMUNION_OUTGOING=8601
export SEAMLESS_COMMUNION_INCOMING=localhost:8602,localhost:8603
python3 communion-peer1.py &

export SEAMLESS_COMMUNION_ID=Peer2
export SEAMLESS_COMMUNION_OUTGOING=8602
export SEAMLESS_COMMUNION_INCOMING=localhost:8601,localhost:8603
sleep 3
python3 communion-peer2.py &

if false; then
export SEAMLESS_COMMUNION_ID=Peer3
export SEAMLESS_COMMUNION_OUTGOING=8603
export SEAMLESS_COMMUNION_INCOMING=localhost:8601,localhost:8602
(sleep 4 && python3 communion-peer2.py) &
fi

wait
