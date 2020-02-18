rm -f twopi-colored-service.seamless
###docker run --rm -v /tmp/redis:/data redis bash -c 'rm -rf /data/*'
###redisID=`docker run --rm -p 6379:6379 --name redis-container -v /tmp/redis:/data -d redis redis-server --appendonly yes`

python3 simple-pi-redis.py
python3 ~/seamless-scripts/color-graph-service.py 8 &
sleep 3
python3 ~/seamless-scripts/jobslave.py --time 5 --communion_incoming localhost:8600 &
sleep 3
python3 twopi-graph-service-submit.py twopi.seamless twopi-colored-service.seamless
wait
md5sum twopi-colored-service.seamless

###docker stop $redisID