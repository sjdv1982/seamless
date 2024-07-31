seamless-delegate-stop
rm -rf /tmp/dummy-db
export SEAMLESS_HASHSERVER_DIRECTORY=/tmp/dummy-db/buffers
export SEAMLESS_DATABASE_DIRECTORY=/tmp/dummy-db/database
export SEAMLESS_READ_BUFFER_FOLDERS=/tmp/dummy-db/buffers
seamless-delegate none

