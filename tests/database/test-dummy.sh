#!/bin/bash

export SEAMLESS_DATABASE_DIR=/tmp/seamless-db
export SEAMLESS_DATABASE_PORT=5522
export SEAMLESS_DATABASE_IP=0.0.0.0

rm -rf $SEAMLESS_DATABASE_DIR
mkdir $SEAMLESS_DATABASE_DIR

function filesystem() {
    echo 'File system:'
    for i in `find $SEAMLESS_DATABASE_DIR -type f`; do
        echo $i
        cat $i
        echo
    done
}

echo 'Stage 1'
python3 -u ../../tools/database.py > test-dummy-server-stage1.log 2>&1 &
p2=$!
echo 'Database server running'
sleep 3
python3 -u dummy-database-client.py
echo
kill -1 $p2
disown $p2
filesystem
echo
echo 'Server log'
cat test-dummy-server-stage1.log
echo '/Server log'
echo

echo 'Stage 2'
python3 -u ../../tools/database.py > test-dummy-server-stage2.log 2>&1 &
p2=$!
echo 'Database server running'
sleep 3
python3 -u dummy2-database-client.py
filesystem
python3 -u dummy2a-database-client.py
filesystem
kill -1 $p2
disown $p2
echo 'Server log'
cat test-dummy-server-stage2.log
echo '/Server log'
echo

rm -f test-dummy-server-stage[12].log