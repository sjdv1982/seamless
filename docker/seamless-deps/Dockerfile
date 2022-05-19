FROM jupyter/scipy-notebook@sha256:a891adee079e8c3eee54fef732cd282fe6b06c5fabe1948b9b11e07144526865
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
USER root
COPY conda/seamless-deps-environment.yml seamless-deps-environment.yml
RUN apt update && apt install -y gfortran curl gdb iputils-ping apt-transport-https ca-certificates gnupg-agent software-properties-common 
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add - && sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable" && sudo apt update && sudo apt install -y docker-ce-cli
RUN conda config --env --set channel_priority strict && conda env update --name base --file seamless-deps-environment.yml
