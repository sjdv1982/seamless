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
echo

rm -f dummy-bufferfolder/d861fc9d20c465ff20d76269a155be799dd70f9d27475b04082e41680cda2a00
echo 'fingertip-database4.py'
python fingertip-database4.py
echo

rm -f dummy-bufferfolder/d861fc9d20c465ff20d76269a155be799dd70f9d27475b04082e41680cda2a00
echo 'fingertip-database5.py'
python fingertip-database5.py
echo

seamless-delegate-stop 1>&2
rm -rf dummy-directory dummy-bufferfolder dummy-database
