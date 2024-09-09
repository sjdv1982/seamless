rm -rf temp-bufferdir
currdir=`python -c 'import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))' $0`
export SEAMLESS_HASHSERVER_DIRECTORY=$currdir/temp-bufferdir
seamless-delegate-stop >& /dev/null
seamless-delegate none-devel >& /dev/null
seamless-upload testfolder

function ftest() {
    diff -r testfolder2 testfolder
    diff testfolder2.INDEX testfolder.INDEX
    diff testfolder2.CHECKSUM testfolder.CHECKSUM
    rm -rf testfolder2.CHECKSUM testfolder2.INDEX testfolder2.buffersize
}

echo 1
seamless-download -vvv -o testfolder2 testfolder
ftest

echo 1a
echo extra > testfolder2/extra
seamless-download -vvv -o testfolder2 testfolder
ftest

echo 1b
rm -rf testfolder2/sub
seamless-download -vvv -o testfolder2 testfolder
ftest

rm -rf testfolder2

echo 1c
seamless-download --index -o testfolder2 testfolder
cd testfolder2
seamless-buffer-size *.CHECKSUM */*.CHECKSUM > ../testfolder.buffersize
cd ..
rm -rf testfolder2 testfolder2.CHECKSUM testfolder2.INDEX

echo 2
cs=$(cat testfolder.CHECKSUM)
seamless-download --directory -o testfolder2 $cs
ftest
rm -rf testfolder2

echo 3
seamless-download --directory --index -o testfolder2 $cs
cd testfolder2
seamless-buffer-size *.CHECKSUM */*.CHECKSUM > ../testfolder2.buffersize
cd ..
diff testfolder.buffersize testfolder2.buffersize
seamless-download testfolder2/*.CHECKSUM testfolder2/*/*.CHECKSUM
rm -rf testfolder2/*.CHECKSUM testfolder2/*/*.CHECKSUM
ftest
rm -rf testfolder2

seamless-delegate-stop >& /dev/null
rm -rf temp-bufferdir
rm -rf testfolder.buffersize testfolder.CHECKSUM testfolder.INDEX