rm -f twopi-colored-jobmaster.seamless
###docker run --rm -v /tmp/redis:/data redis bash -c 'rm -rf /data/*'
###redisID=`docker run --rm -p 6379:6379 --name redis-container -v /tmp/redis:/data -d redis redis-server --appendonly yes`

python3 simple-pi-redis.py
python3 ~/seamless-scripts/jobslave.py --time 5 &
sleep 2
python3 ~/seamless-scripts/color-graph-jobmaster.py twopi.seamless twopi-colored-jobmaster.seamless
wait
md5sum twopi-colored-jobmaster.seamless

###docker stop $redisID