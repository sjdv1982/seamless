rm -rf /tmp/PIN-FILESYSTEM-FOLDER
rm -rf /tmp/dummy-bufferfolder
cp -r testfolder /tmp/PIN-FILESYSTEM-FOLDER
mkdir /tmp/dummy-bufferfolder
unset SEAMLESS_ASSISTANT_IP
unset SEAMLESS_ASSISTANT_PORT
unset SEAMLESS_READ_BUFFER_FOLDERS
unset SEAMLESS_READ_BUFFER_SERVERS
unset SEAMLESS_WRITE_BUFFER_SERVER
echo 'Run 1'
python3 -u pin-filesystem.py
export SEAMLESS_READ_BUFFER_FOLDERS=/tmp/dummy-bufferfolder
echo 'Upload folder '
seamless-upload -v --dest /tmp/dummy-bufferfolder /tmp/PIN-FILESYSTEM-FOLDER
echo 'Run 2'
python3 -u pin-filesystem.py
echo 'Deploy folder '
seamless-bufferdir-deploy-deepfolder $(cat /tmp/PIN-FILESYSTEM-FOLDER.CHECKSUM) /tmp/dummy-bufferfolder
echo 'Run 3'
python3 -u pin-filesystem.py
rm -rf /tmp/PIN-FILESYSTEM-FOLDER
rm -rf /tmp/PIN-FILESYSTEM-FOLDER.*
rm -rf /tmp/dummy-bufferfolder