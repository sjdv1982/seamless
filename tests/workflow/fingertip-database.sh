rm -rf dummy-directory dummy-bufferfolder dummy-database
mkdir dummy-directory dummy-bufferfolder dummy-database
export SEAMLESS_HASHSERVER_DIRECTORY=$(pwd)/dummy-bufferfolder
export SEAMLESS_DATABASE_DIRECTORY=$(pwd)/dummy-database
seamless-delegate-stop 1>&2
seamless-delegate none 1>&2

echo 'fingertip-database1.py'
python fingertip-database1.py
echo

echo 'fingertip-database2.py'
python fingertip-database2.py
echo

echo 'fingertip-database3.py'
python fingertip-database3.py
echo

echo 'Must not exist:'
ls dummy-bufferfolder/39dacbda510b82b6fec0680fb7beb110eef660f5daef6c129ef1abfde1d4d331

seamless-delegate-stop 1>&2
rm -rf dummy-directory dummy-bufferfolder dummy-database
