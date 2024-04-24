#!/bin/bash
sleep 2
seamless -c 'python pilot/add.py pilot/two.txt pilot/three.txt > five.txt' &
seamless -c 'python pilot/add.py pilot/three.txt pilot/four.txt > seven.txt' &
sleep 0.5
seamless -c 'python pilot/add.py five.txt pilot/three.txt > eight.txt' &
seamless -c 'python pilot/add.py seven.txt pilot/two.txt > nine.txt' &
wait
cat eight.txt
cat nine.txt