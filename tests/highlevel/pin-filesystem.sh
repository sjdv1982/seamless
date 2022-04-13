db=/tmp/PIN-FILESYSTEM-TEST-DB
rm -rf $db
mkdir $db
export SEAMLESS_DATABASE_DIR=$db
export SEAMLESS_DATABASE_HOST=localhost
export SEAMLESS_DATABASE_PORT=5522
echo 'Share folder'
../../tools/database-run-actions pin-filesystem.cson
../../tools/database-share-deepfolder-directory --collection testfolder
echo
echo 'Run 1'
python3 -u pin-filesystem.py > pin-filesystem.log 2>&1
checksum=`tail -1 pin-filesystem.log`
cat pin-filesystem.log
rm -f pin-filesystem.log
echo
echo 'Start database'
python3 ../../tools/database.py > $db.log 2>&1 &
sleep 2
echo
echo 'Run 2'
python3 -u pin-filesystem.py
kill %1
echo
echo 'Server log'
cat $db.log
echo ''
exit ###
rm -rf $db
rm -rf /tmp/PIN-FILESYSTEM-FOLDER
rm -f $db.log