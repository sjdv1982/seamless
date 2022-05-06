rm -f twopi-colored-jobmaster.seamless

python3 simple-pi-database.py
python3 ~/seamless-scripts/jobslave.py --database --time 5 &
sleep 2
python3 ~/seamless-scripts/color-graph-jobmaster.py twopi.seamless twopi-colored-jobmaster.seamless
wait
md5sum twopi-colored-jobmaster.seamless
