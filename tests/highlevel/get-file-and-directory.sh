#!/bin/bash
rm -rf dummy-directory dummy-bufferfolder
mkdir dummy-directory dummy-bufferfolder
echo Text > dummy-directory/text.txt
mkdir dummy-directory/sub
echo 1 > dummy-directory/sub/one.txt
echo 2 > dummy-directory/sub/two.txt
seamless-upload -v --dest dummy-bufferfolder dummy-directory/text.txt
seamless-upload -v --dest dummy-bufferfolder dummy-directory/sub
echo Repeat, no files will be uploaded...
seamless-upload -v --dest dummy-bufferfolder dummy-directory/text.txt
seamless-upload -v --dest dummy-bufferfolder dummy-directory/sub
seamless-bufferdir-deploy-deepfolder $(cat dummy-directory/sub.CHECKSUM) dummy-bufferfolder
export SEAMLESS_READ_BUFFER_FOLDERS=dummy-bufferfolder
python3 get-file-and-directory.py
rm -rf dummy-directory dummy-bufferfolder
