if [ -z "$SEAMLESS_TOOLS_DIR" ]; then
  export SEAMLESS_TOOLS_DIR=~/seamless-tools
fi

export SEAMLESS_DATABASE_IP=localhost
export SEAMLESS_DATABASE_PORT=5522
db=/tmp/ELISION-TEST-DB
rm -rf $db
mkdir $db
dbconfig='''
host: "0.0.0.0" 
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
echo "$dbconfig" | python3 $SEAMLESS_TOOLS_DIR/database.py /dev/stdin > $db.log 2>&1 &
sleep 1
echo
echo 'Run 2'
python3 -u macro-elision-database.py
echo
echo 'Run 3'
python3 -u macro-elision-database.py
kill `ps -ef | grep $SEAMLESS_TOOLS_DIR/database.py | awk '{print $2}' | tac | awk 'NR > 1'`
echo
echo 'Server log'
cat $db.log
echo ''
rm -rf $db
rm -f $db.log