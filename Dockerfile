FROM jupyter/scipy-notebook@sha256:a891adee079e8c3eee54fef732cd282fe6b06c5fabe1948b9b11e07144526865
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.7.6"
USER root
COPY requirements.txt requirements.txt
RUN apt update && apt install -y gfortran curl gdb iputils-ping redis-tools apt-transport-https ca-certificates gnupg-agent software-properties-common r-base
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add - && sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable" && sudo apt update && sudo apt -y install docker-ce-cli
RUN pip install -r requirements.txt && conda install -c rpbs silk && jupyter-nbextension enable nglview --py --sys-prefix
COPY . /usr/local/src/seamless
RUN rm -rf /usr/local/src/seamless/.git && \
    mkdir /home/jovyan/software && \
    cp -Lr /usr/local/src/seamless/seamless /home/jovyan/software/seamless && \
    cp -Lr /usr/local/src/seamless/tests /home/jovyan/seamless-tests && \
    cp -Lr /usr/local/src/seamless/examples /home/jovyan/seamless-examples && \
    cp -Lr /usr/local/src/seamless/docker/commands /home/jovyan/seamless-docker && \
    cp -Lr /usr/local/src/seamless/scripts /home/jovyan/seamless-scripts && \
    cp -Lr /usr/local/src/seamless/tools /home/jovyan/seamless-tools
RUN chown -R jovyan /home/jovyan && chmod -R g=u /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
