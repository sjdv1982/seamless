db=/tmp/PIN-FILESYSTEM-TEST-DB
rm -rf $db
mkdir $db
export SEAMLESS_DATABASE_DIR=$db
export SEAMLESS_DATABASE_IP=localhost
export SEAMLESS_DATABASE_PORT=5522
echo 'Share folder'
../../tools/database-run-actions $db pin-filesystem.cson
../../tools/database-share-deepfolder-directory $db --collection testfolder
echo
echo 'Run 1'
python3 -u pin-filesystem.py > pin-filesystem.log 2>&1
checksum=`tail -1 pin-filesystem.log`
cat pin-filesystem.log
rm -f pin-filesystem.log
echo
echo 'Start database'
dbconfig='''
host: "0.0.0.0" 
port:  5522
stores: 
    -
      path: "'''$db'''"
      readonly: false
      serve_filenames: true
'''
echo "$dbconfig" | python3 ../../tools/database.py /dev/stdin > $db.log 2>&1 &
sleep 2
echo
echo 'Run 2'
python3 -u pin-filesystem.py
kill `ps -ef | grep database | awk '{print $2}' | tac | awk 'NR > 1'`
echo
echo 'Server log'
cat $db.log
rm -rf $db
rm -rf /tmp/PIN-FILESYSTEM-FOLDER
rm -f $db.log