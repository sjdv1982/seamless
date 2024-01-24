rm -rf /tmp/PIN-FILESYSTEM-FOLDER1
rm -rf /tmp/PIN-FILESYSTEM-FOLDER2
rm -rf /tmp/dummy-bufferfolder
mkdir /tmp/dummy-bufferfolder
unset SEAMLESS_ASSISTANT_IP
unset SEAMLESS_ASSISTANT_PORT
unset SEAMLESS_READ_BUFFER_FOLDERS
unset SEAMLESS_READ_BUFFER_SERVERS
unset SEAMLESS_WRITE_BUFFER_SERVER
echo 'Run 1'
python3 -u pin-filesystem.py
export SEAMLESS_READ_BUFFER_FOLDERS=/tmp/dummy-bufferfolder
echo 'Upload folder 2'
seamless-upload -v --dest /tmp/dummy-bufferfolder /tmp/PIN-FILESYSTEM-FOLDER2
echo 'Run 2'
python3 -u pin-filesystem.py
echo 'Deploy folder 2'
seamless-bufferdir-deploy-deepfolder $(cat /tmp/PIN-FILESYSTEM-FOLDER2.CHECKSUM) /tmp/dummy-bufferfolder
echo 'Run 3'
python3 -u pin-filesystem.py
echo 'Upload and deploy folder 1'
seamless-upload -v --dest /tmp/dummy-bufferfolder /tmp/PIN-FILESYSTEM-FOLDER1
seamless-bufferdir-deploy-deepfolder $(cat /tmp/PIN-FILESYSTEM-FOLDER1.CHECKSUM) /tmp/dummy-bufferfolder
echo 'Run 4'
python3 -u pin-filesystem.py
rm -rf /tmp/PIN-FILESYSTEM-FOLDER1
rm -rf /tmp/PIN-FILESYSTEM-FOLDER1.*
rm -rf /tmp/PIN-FILESYSTEM-FOLDER2
rm -rf /tmp/PIN-FILESYSTEM-FOLDER2.*
rm -rf /tmp/dummy-bufferfolder