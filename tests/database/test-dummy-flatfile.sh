docker run --rm -d --name redis-dummy1 -p 6379:6379  -u `id -u`:`id -g` redis redis-server --save "" --maxmemory 1gb --maxmemory-policy volatile-ttl \
 > redis-dummy1.log 2>&1 &
echo 'Redis container running'
sleep 5

mkdir -p /tmp/seamless-db
python3 -u ../../tools/database.py example-config.yaml > test-dummy-flatfile-server.log 2>&1 &
p2=$!
echo 'Database server running'
sleep 5
python3 -u dummy-database-client.py
echo
echo 'Database keys:'
seamless redis-cli -h 172.17.0.1 -p 6379 -c keys '???:*'
echo
echo 'File system:'
for i in `find /tmp/seamless-db -type f`; do
    echo $i
    cat $i
    echo
done
echo
echo 'Stage 2'
python3 -u dummy2a-database-client.py
echo
echo 'Database keys:'
seamless redis-cli -h 172.17.0.1 -p 6379 -c keys '???:*'
echo
echo 'File system:'
for i in `find /tmp/seamless-db -type f`; do
    echo $i
    cat $i
    echo
done

kill -1 $p2
disown $p2
echo 'Server log'
cat test-dummy-flatfile-server.log
echo

docker stop redis-dummy1
rm -f *.log