seamless-delegate-stop >& /dev/null
export SEAMLESS_DATABASE_IP=localhost
export SEAMLESS_DATABASE_PORT=5522
db=/tmp/ELISION-TEST-DB
export SEAMLESS_DATABASE_DIRECTORY=$db
rm -rf $db
mkdir $db
echo 'Run 1'
python3 -u macro-elision-database.py
echo 'Start database'
seamless-delegate-stop >& /dev/null
seamless-delegate none >& /dev/null
sleep 1
echo
echo 'Run 2'
python3 -u macro-elision-database.py
echo
echo 'Run 3'
python3 -u macro-elision-database.py
echo
echo 'Server log'
docker logs delegate-database-1
echo ''
seamless-delegate-stop >& /dev/null
rm -rf $db
