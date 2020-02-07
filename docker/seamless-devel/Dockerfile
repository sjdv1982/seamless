FROM jupyter/scipy-notebook@sha256:60b6dd2bf2347d260603d6609ddd97c3dd755f4c5e9fa8842a58855faf006328
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
COPY requirements.txt requirements.txt
RUN apt update && apt install -y gfortran
RUN pip install -r requirements.txt
RUN ln -s /seamless/tests /home/jovyan/seamless-tests && \
    ln -s /seamless/examples /home/jovyan/seamless-examples && \
    ln -s /seamless/docker/commands /home/jovyan/seamless-docker && \
    ln -s /seamless/scripts /home/jovyan/seamless-scripts
RUN chown -R jovyan /home/jovyan
