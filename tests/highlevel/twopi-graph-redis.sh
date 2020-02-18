###docker run --rm -v /tmp/redis:/data redis bash -c 'rm -rf /data/*'
###redisID=`docker run --rm -p 6379:6379 --name redis-container -v /tmp/redis:/data -d redis redis-server --appendonly yes`

rm -f twopi-colored.seamless
python3 simple-pi-redis.py
python3 twopi-graph-redis.py
python3 ~/seamless-scripts/color-graph.py twopi.seamless twopi-colored.seamless
md5sum twopi-colored.seamless

###docker stop $redisID