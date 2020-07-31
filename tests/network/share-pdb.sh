#/!/bin/bash

set -u -e
# first run Seamless-database and jobslave.sh
seamless-devel-add-zip share-pdb.zip

seamlessdir=`python3 -c 'import seamless,os;print(os.path.dirname(seamless.__file__))'`/../

bridge_ip=$(docker network inspect bridge \
  | python3 -c '''
import json, sys
bridge = json.load(sys.stdin)
print(bridge[0]["IPAM"]["Config"][0]["Gateway"])
''')

name=share-pdb
communion_incoming=$bridge_ip:8602
docker run --rm \
  --name $name \
  -v $seamlessdir:/seamless \
  -e "PYTHONPATH=/seamless" \
  -e "SEAMLESS_DATABASE_HOST="$bridge_ip \
  -e "SHARESERVER_ADDRESS=0.0.0.0" \
  -e "SEAMLESS_COMMUNION_ID="$name \
  -e "SEAMLESS_COMMUNION_INCOMING="$communion_incoming \
  -v `pwd`:/cwd \
  --workdir /cwd \
  -u jovyan \
  -it \
  seamless-devel ipython3 -i /home/jovyan/seamless-scripts/serve-graph.py -- \
    share-pdb.seamless --database --ncores 0 \
    --communion_id $name \
    --interactive
