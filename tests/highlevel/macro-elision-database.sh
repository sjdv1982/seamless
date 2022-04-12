db=/tmp/ELISION-TEST-DB
rm -rf $db
mkdir $db
export SEAMLESS_DATABASE_DIR=$db
export SEAMLESS_DATABASE_HOST=localhost
export SEAMLESS_DATABASE_PORT=5522
echo 'Run 1'
python3 -u macro-elision-database.py
echo 'Start database'
python3 ../../tools/database.py > $db.log 2>&1 &
sleep 1
echo
echo 'Run 2'
python3 -u macro-elision-database.py
echo
echo 'Run 3'
python3 -u macro-elision-database.py
kill %1
echo
echo 'Server log'
cat $db.log
echo ''
rm -rf $db
rm -f $db.log