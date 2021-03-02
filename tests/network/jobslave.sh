 # first run Seamless-database

set -u -e

# - Current directory is mounted to /cwd, and the command is executed there
# - Seamless has access to the Docker daemon, so it can launch its own Docker
#    containers via the Docker transformer. This works only under Linux.
#    NOTE: THIS IS A BIG SECURITY HOLE, IT CAN GIVE ROOT ACCESS TO YOUR SYSTEM

seamlessdir=$SEAMLESSDIR

bridge_ip=$(docker network inspect bridge \
  | python3 -c '''
import json, sys
bridge = json.load(sys.stdin)
print(bridge[0]["IPAM"]["Config"][0]["Gateway"])
''')

name=JOBSLAVE
docker run --rm \
  --name $name \
  -v $seamlessdir:/seamless \
  -e "PYTHONPATH=/seamless" \
  -e "SEAMLESS_DATABASE_HOST="$bridge_ip \
  -e SEAMLESS_COMMUNION_OUTGOING_ADDRESS=0.0.0.0 \
  -p 8602:8602 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --group-add $(getent group docker | cut -d: -f3) \
  --user $(id -u):$(id -g) \
  -it \
  seamless-devel ipython3 -i /home/jovyan/seamless-scripts/jobslave.py \
    -- --communion_id $name --interactive
