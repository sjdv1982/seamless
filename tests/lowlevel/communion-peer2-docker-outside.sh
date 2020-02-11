#!/bin/bash
export SEAMLESS_COMMUNION_ID=Peer2
port=$(docker port Peer1 | grep 8601 | sed 's/:/ /' | awk '{print $4}')
export SEAMLESS_COMMUNION_INCOMING=localhost:$port
python3 communion-peer2.py
