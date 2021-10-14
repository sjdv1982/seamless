FROM continuumio/miniconda3
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.7"
USER root
RUN conda install 'python==3.8.8' pip
RUN export RPY2_CFFI_MODE=ABI && pip install -r https://raw.githubusercontent.com/sjdv1982/seamless/stable/requirements.txt
RUN pip install -r https://raw.githubusercontent.com/sjdv1982/seamless/stable/requirements-extra.txt
RUN conda install -c conda-forge matplotlib psutil --yes && \
    conda install conda --yes
RUN conda install -c rpbs  -c conda-forge silk seamless-framework --yes
#RUN apt update && apt install -y gfortran gdb

