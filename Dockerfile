FROM jupyter/scipy-notebook@sha256:60b6dd2bf2347d260603d6609ddd97c3dd755f4c5e9fa8842a58855faf006328
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . /usr/local/src/seamless
RUN rm -rf /usr/local/src/seamless/.git && \
    mkdir /home/jovyan/software && \
    cp -Lr /usr/local/src/seamless/seamless /home/jovyan/software/seamless && \
    cp -Lr /usr/local/src/seamless/tests /home/jovyan/seamless-tests && \
    cp -Lr /usr/local/src/seamless/examples /home/jovyan/seamless-examples && \
    cp -Lr /usr/local/src/seamless/docker/commands /home/jovyan/seamless-docker
RUN chown -R jovyan /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
