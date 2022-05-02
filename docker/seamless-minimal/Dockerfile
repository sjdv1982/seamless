FROM continuumio/miniconda3
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.8"
USER root
COPY seamless /usr/local/seamless
COPY docker/seamless-minimal/environment.yml /seamless-minimal/environment.yml
RUN export RPY2_CFFI_MODE=ABI
ENV PYTHONPATH /usr/local:$PYTHONPATH
RUN cp /root/.bashrc /.bashrc && chmod 777 /.bashrc \
&& mkdir /.conda && chmod 777 /.conda && chmod -R 777 /seamless-minimal
