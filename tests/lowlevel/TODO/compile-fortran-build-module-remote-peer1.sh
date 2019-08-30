docker run --rm -p 6379:6379 --name redis-container -v /tmp/redis:/data -d redis redis-server --appendonly yes
redis-cli flushall

python3 ../../scripts/build-module-slave.py  &

sleep 20
echo STOP

redis-cli flushall
docker stop redis-container

kill -1 %1