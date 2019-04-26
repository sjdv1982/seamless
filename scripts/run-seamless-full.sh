docker run \
  --rm \
  --network=host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /tmp:/tmp \
  seamless start-notebook.sh  \
  --ip='0.0.0.0' --NotebookApp.token='' --NotebookApp.password='' \
  $*
