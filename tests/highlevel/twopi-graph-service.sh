rm -f twopi-colored-service.seamless

python3 simple-pi-database.py
python3 ~/seamless-scripts/color-graph-service.py 8 &
sleep 3
python3 ~/seamless-scripts/jobslave.py --database --time 5 --communion_incoming localhost:8600 &
sleep 3
python3 twopi-graph-service-submit.py twopi.seamless twopi-colored-service.seamless
wait
md5sum twopi-colored-service.seamless
