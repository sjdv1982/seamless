rm -rf /tmp/PIN-FILESYSTEM-FOLDER1
rm -rf /tmp/PIN-FILESYSTEM-FOLDER2
db=/tmp/PIN-FILESYSTEM-TEST-DB
rm -rf $db
mkdir $db
export SEAMLESS_DATABASE_DIR=$db
export SEAMLESS_DATABASE_HOST=localhost
export SEAMLESS_DATABASE_PORT=5522
echo 'Run 1'
python3 -u pin-filesystem.py > pin-filesystem.log 2>&1
checksum=`tail -1 pin-filesystem.log`
cat pin-filesystem.log
rm -f pin-filesystem.log
echo 'Start database'
python3 ../../tools/database.py > $db.log 2>&1 &
sleep 2
echo
echo 'Run 2'
python3 -u pin-filesystem.py
echo
echo 'Share folder 2 and restart database'
kill %1
../../tools/database-run-actions pin-filesystem-2.cson
../../tools/database-share-deepfolder-directory --collection testfolder2
python3 ../../tools/database.py > $db.log 2>&1 &
sleep 2
echo
echo 'Run 3'
python3 -u pin-filesystem.py
echo
echo 'Share folder 1 and restart database'
kill %1
../../tools/database-run-actions pin-filesystem-1.cson
../../tools/database-share-deepfolder-directory --collection testfolder1
python3 ../../tools/database.py > $db.log 2>&1 &
sleep 2
echo
echo 'Delete transformation result'
python3 ../../scripts/delete-transformation-result.py $checksum
echo
echo 'Run 4'
python3 -u pin-filesystem.py
kill %1
echo
echo 'Server log'
cat $db.log
echo ''
rm -rf $db
rm -rf /tmp/PIN-FILESYSTEM-FOLDER1
rm -rf /tmp/PIN-FILESYSTEM-FOLDER2
rm -f $db.log