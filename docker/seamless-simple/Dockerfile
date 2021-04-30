FROM continuumio/miniconda3
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.6"
USER root
RUN apt update && apt install -y gfortran gdb
RUN conda install 'python==3.7.3' pip
RUN pip install -r https://raw.githubusercontent.com/sjdv1982/seamless/experimental/requirements.txt
RUN pip install -r https://raw.githubusercontent.com/sjdv1982/seamless/experimental/requirements-extra.txt
RUN conda install -c rpbs silk seamless-framework
