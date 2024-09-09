exist=$(docker compose ls | awk 'NF > 1 && $1 == "hashserver"' | wc -l)
if [ $exist != "0" ]; then
    echo 'A Docker hashserver is already running, kill it before testing'
    exit 1
fi

rm -rf /tmp/bufferdir
echo 0
python buffer_remote0.py 0  # vault layout.
echo ''

buffer_write_server=$SEAMLESS_WRITE_BUFFER_SERVER
export HASHSERVER_WRITABLE=0
export HASHSERVER_LAYOUT=vault
unset SEAMLESS_WRITE_BUFFER_SERVER
seamless-hashserver /tmp/bufferdir/ >& /dev/null

echo 1
python buffer_remote1.py
docker stop hashserver-hashserver-1
rm -rf /tmp/bufferdir
echo ''

export SEAMLESS_WRITE_BUFFER_SERVER=$buffer_write_server
export HASHSERVER_WRITABLE=1
unset HASHSERVER_LAYOUT
mkdir -p /tmp/bufferdir
seamless-hashserver /tmp/bufferdir/ >& /dev/null

echo 0a
python buffer_remote0.py 1  # flat
echo ''

echo 1a
python buffer_remote1.py
echo ''

echo 2
python buffer_remote2.py
echo ''
echo 3
python buffer_remote3.py
echo ''
docker stop hashserver-hashserver-1
echo ''

export SEAMLESS_READ_BUFFER_SERVERS=""
export SEAMLESS_WRITE_BUFFER_SERVER=""
export SEAMLESS_READ_BUFFER_FOLDERS=/tmp/bufferdir

echo 1b
python buffer_remote1.py
echo ''
echo 3b
python buffer_remote3.py
echo ''

rm -rf /tmp/bufferdir
