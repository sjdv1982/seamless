#!/bin/bash
#set -u

rm -rf dummy-directory dummy-bufferfolder
export SEAMLESS_HASHSERVER_DIRECTORY=$(pwd)/dummy-bufferfolder
seamless-delegate-stop > /dev/null 2>&1 
seamless-delegate none > /dev/null 2>&1
mkdir dummy-directory
echo '1234' > dummy-directory/1234.txt
seamless-upload dummy-directory/1234.txt
python3 direct-read-hashserver-dir.py

seamless-delegate-stop > /dev/null 2>&1 
python3 direct-read-hashserver-dir.py
export SEAMLESS_READ_BUFFER_FOLDERS=$SEAMLESS_HASHSERVER_DIRECTORY
python3 direct-read-hashserver-dir.py

rm -rf  dummy-bufferfolder
export SEAMLESS_HASHSERVER_DIRECTORY=$(pwd)/dummy-bufferfolder
export HASHSERVER_LAYOUT=prefix
seamless-delegate none > /dev/null 2>&1
seamless-upload dummy-directory/1234.txt
python3 direct-read-hashserver-dir.py

seamless-delegate-stop > /dev/null 2>&1 
python3 direct-read-hashserver-dir.py

seamless-delegate-stop 1>&2
rm -rf dummy-directory dummy-bufferfolder
