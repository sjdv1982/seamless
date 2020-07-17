FROM jupyter/scipy-notebook@sha256:60b6dd2bf2347d260603d6609ddd97c3dd755f4c5e9fa8842a58855faf006328
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.3.3"
USER root
COPY requirements.txt requirements.txt
RUN apt update && apt install -y gfortran curl gdb iputils-ping redis-tools
RUN pip install -r requirements.txt && jupyter-nbextension enable nglview --py --sys-prefix
COPY . /usr/local/src/seamless
RUN rm -rf /usr/local/src/seamless/.git && \
    mkdir /home/jovyan/software && \
    cp -Lr /usr/local/src/seamless/seamless /home/jovyan/software/seamless && \
    cp -Lr /usr/local/src/seamless/tests /home/jovyan/seamless-tests && \
    cp -Lr /usr/local/src/seamless/examples /home/jovyan/seamless-examples && \
    cp -Lr /usr/local/src/seamless/docker/commands /home/jovyan/seamless-docker && \
    cp -Lr /usr/local/src/seamless/scripts /home/jovyan/seamless-scripts
RUN chown -R jovyan /home/jovyan && echo 'umask 000' >> /home/jovyan/.bashrc
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
