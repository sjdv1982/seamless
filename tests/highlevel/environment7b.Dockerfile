FROM seamless-devel
USER jovyan
COPY pytorch-environment.yml .
RUN source /home/jovyan/.bashrc && mamba env update -n base --file pytorch-environment.yml