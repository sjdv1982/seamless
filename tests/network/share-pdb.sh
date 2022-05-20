#/!/bin/bash

set -u -e

echo $SEAMLESSDIR > /dev/null
export SEAMLESS_DOCKER_IMAGE=seamless-devel
export SEAMLESS_COMMUNION_PORT=8602

set -u -e
# first run Seamless-database and jobslave --database
seamless-add-zip share-pdb.zip

rundir=`python3 -c 'import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))' share-pdb.seamless`

cd ${rundir}

export SEAMLESS_COMMUNION_ID=share-pdb
export SEAMLESS_DOCKER_CONTAINER_NAME=share-pdb

seamless-serve-graph-interactive share-pdb.seamless \
  --database --ncores 0 --communion

#seamless-serve-graph share-pdb.seamless \
#  --database --ncores 0 --communion  