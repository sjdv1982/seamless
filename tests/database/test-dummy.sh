docker run --rm -d --name redis-dummy1 -p 6380:6379  -u `id -u`:`id -g` redis redis-server --save "" --maxmemory 1gb --maxmemory-policy volatile-ttl \
 > redis-dummy1.log 2>&1 &
docker run --rm -d --name redis-dummy2 -p 6381:6379  -u `id -u`:`id -g` redis redis-server --save "" --maxmemory 1gb --maxmemory-policy volatile-ttl \
 > redis-dummy2.log 2>&1 &
echo 'Redis containers running'
sleep 5

echo 'Stage 1'
python3 -u ../../tools/database.py dummy1-config.yaml > test-dummy1-server.log 2>&1 &
p2=$!
echo 'Database server running'
sleep 5
python3 -u dummy-database-client.py
echo
echo 'Database keys:'
echo 'Database 1'
seamless redis-cli -h 172.17.0.1 -p 6380 -c keys '???-*'
echo
echo 'Database 2'
seamless redis-cli -h 172.17.0.1 -p 6381 -c keys '???-*'
echo
kill -1 $p2
disown $p2
echo 'Server log'
cat test-dummy1-server.log
echo

echo 'Stage 2'
python3 -u ../../tools/database.py dummy2-config.yaml > test-dummy-server-stage1.log 2>&1 &
p2=$!
echo 'Database server running'
sleep 5
python3 -u dummy2-database-client.py
echo
echo 'Database keys:'
echo 'Database 1'
seamless redis-cli -h 172.17.0.1 -p 6380 -c keys '???-*'
echo
echo 'Database 2'
seamless redis-cli -h 172.17.0.1 -p 6381 -c keys '???-*'
echo
echo 'Stage 2a'
sleep 3
python3 -u dummy2a-database-client.py
echo
echo 'Database keys:'
echo 'Database 1'
seamless redis-cli -h 172.17.0.1 -p 6380 -c keys '???-*'
echo
echo 'Database 2'
seamless redis-cli -h 172.17.0.1 -p 6381 -c keys '???-*'
echo
kill -1 $p2
disown $p2
echo 'Server log'
cat test-dummy1-server.log
echo

docker stop redis-dummy1 redis-dummy2
rm -f *.log