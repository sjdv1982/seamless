docker run -v \
  `pwd`:/home/jovyan/work -v ~/seamless:/seamless \
  -e "PYTHONPATH=/seamless" -e /home/jovyan/work  \
  --network=host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /tmp:/tmp \
  seamless-devel start-notebook.sh  \
  --ip='0.0.0.0' --NotebookApp.token='' --NotebookApp.password=''