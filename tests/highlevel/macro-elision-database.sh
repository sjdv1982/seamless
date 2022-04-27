db=/tmp/ELISION-TEST-DB
rm -rf $db
mkdir $db
dbconfig='''
host: "localhost" 
port:  5522
stores: 
    -
      path: "'''$db'''"
      readonly: false
      serve_filenames: true
'''
echo 'Run 1'
python3 -u macro-elision-database.py
echo 'Start database'
echo "$dbconfig" | python3 ../../tools/database.py /dev/stdin > $db.log 2>&1 &
sleep 1
echo
echo 'Run 2'
python3 -u macro-elision-database.py
echo
echo 'Run 3'
python3 -u macro-elision-database.py
kill `ps -ef | grep ../../tools/database.py | awk '{print $2}' | tac | awk 'NR > 1'`
echo
echo 'Server log'
cat $db.log
echo ''
rm -rf $db
rm -f $db.log