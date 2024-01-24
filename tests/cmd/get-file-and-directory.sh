#!/bin/bash
set -u
ASSISTANT=$1
rm -rf dummy-directory dummy-bufferfolder
mkdir dummy-directory dummy-bufferfolder
export SEAMLESS_READ_BUFFER_FOLDERS=$(pwd)/dummy-bufferfolder
seamless-delegate-stop >& /dev/stderr
seamless-delegate $ASSISTANT >& /dev/stderr

echo Text > dummy-directory/text.txt
mkdir dummy-directory/sub
echo 1 > dummy-directory/sub/one.txt
echo 2 > dummy-directory/sub/two.txt
seamless-upload -v --dest dummy-bufferfolder dummy-directory/text.txt >& /dev/stdout
seamless-upload -v --dest dummy-bufferfolder dummy-directory/sub >& /dev/stdout
echo Repeat, no files will be uploaded...
seamless-upload -v --dest dummy-bufferfolder dummy-directory/text.txt >& /dev/stdout
seamless-upload -v --dest dummy-bufferfolder dummy-directory/sub >& /dev/stdout
seamless-bufferdir-deploy-deepfolder $(cat dummy-directory/sub.CHECKSUM) dummy-bufferfolder
rm -rf dummy-directory/sub
rm -rf dummy-directory/text.txt
seamless 'cat dummy-directory/text.txt' >& /dev/stdout
seamless 'cd dummy-directory/sub; head *' >& /dev/stdout
rm -rf dummy-directory dummy-bufferfolder
