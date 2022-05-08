Howto
=====

- Define the Seamless Singularity container file as an environmental variable, e.g:
export SEAMLESS_MINIMAL_SINGULARITY_IMAGE=seamless-minimal.sif

- build the Seamless Singularity container:
singularity build --fakeroot $SEAMLESS_MINIMAL_SINGULARITY_IMAGE docker://rpbs/seamless-minimal:0.8

- You can then use the commands in this folder as drop-in replacements for the seamless-cli commands, without installing Docker.