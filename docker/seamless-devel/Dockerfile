FROM jupyter/scipy-notebook@sha256:60b6dd2bf2347d260603d6609ddd97c3dd755f4c5e9fa8842a58855faf006328
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
USER root
COPY requirements.txt requirements.txt
RUN apt update && apt install -y gfortran curl gdb iputils-ping redis-tools apt-transport-https ca-certificates gnupg-agent software-properties-common
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add - && sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable" && sudo apt update && sudo apt install -y docker-ce-cli
RUN pip install -r requirements.txt && conda install -c rpbs silk && jupyter-nbextension enable nglview --py --sys-prefix
RUN mkdir /home/jovyan/software && \
    ln -s /seamless/seamless /home/jovyan/software/seamless && \
    ln -s /seamless/tests /home/jovyan/seamless-tests && \
    ln -s /seamless/examples /home/jovyan/seamless-examples && \
    ln -s /seamless/docker/commands /home/jovyan/seamless-docker && \
    ln -s /seamless/scripts /home/jovyan/seamless-scripts && \
    ln -s /seamless/tools /home/jovyan/seamless-tools
RUN chown -R jovyan /home/jovyan && chmod -R g=u /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
