Seamless: a cell-based reactive programming framework
=====================================================

Seamless is a framework to set up protocols (workflows) and computations that respond to changes in cells. Cells define the input data as well as the source code of the computations, and all cells can be edited interactively. 

The main application domains are scientific computing, scientific web services, data visualization, and interactive development of algorithms. 

Protocols, computations and results are all represented as directed acyclic graphs that consist of cell checksums. This makes them strongly interoperable and reproducible. Unlike other workflow systems, Seamless graphs are self-contained and do not depend on the content of external files, URLs, identifiers, version numbers, or other kinds of metadata. 

**Installation**: 

Seamless is meant to run from inside a Docker container. It can be installed using the following methods:

- From DockerHub:
```
# Pull docker image
docker pull rpbs/seamless

# Obtain Seamless command line tools (bash)
c=$(docker create rpbs/seamless); docker cp $c:/home/jovyan/seamless-docker ~/seamless-docker; docker rm $c
```
Finally, add ~/seamless-docker to \$PATH. 

This can be done with the following line in your .bashrc:
```export PATH=$PATH:~/seamless-docker```


- From GitHub:
```
# Build docker image
git clone https://github.com/sjdv1982/seamless.git
cd seamless
docker build . -t rpbs/seamless
```
Then, add ~/seamless/docker/commands to \$PATH. 
This can be done with the following line in your .bashrc:

```export PATH=$PATH:~/seamless/docker/commands```


- From pip (inside a Dockerfile)

*NOTE: This is currently not working*
The master branch of Seamless will soon be released as version 0.2.
For now, "pip install seamless-framework" will not work, as it points to the old version 0.1.

**Getting started**:

Run the command ```jupyter-seamless``` to fire up a Jupyter server that runs from inside the Docker image.
