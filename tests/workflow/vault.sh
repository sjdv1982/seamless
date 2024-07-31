#!/bin/bash

rm /tmp/seamless-vault -rf
python3 save-vault.py
python3 load-vault.py
rm /tmp/seamless-vault -rf
