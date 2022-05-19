FROM continuumio/miniconda3
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.8"
USER root
RUN apt update && apt install -y gcc g++ gfortran && export RPY2_CFFI_MODE=ABI
COPY seamless-minimal/environment.yml /seamless-minimal/environment.yml
COPY seamless /usr/local/software/seamless
RUN git clone https://github.com/sjdv1982/seamless-tools && \
  mv seamless-tools/scripts /usr/local/seamless-scripts
ENV PYTHONPATH /usr/local/software:$PYTHONPATH
RUN cp /root/.bashrc /.bashrc && chmod 777 /.bashrc \
&& mkdir /.conda && chmod 777 /.conda && chmod -R 777 /seamless-minimal \
&& chmod -R 777 /usr/local/software && chmod -R 777 /usr/local/seamless-scripts