FROM jupyter/scipy-notebook@sha256:60b6dd2bf2347d260603d6609ddd97c3dd755f4c5e9fa8842a58855faf006328
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY seamless/ /home/jovyan/software/seamless
COPY tests/ /home/jovyan/seamless-tests/
COPY docker/commands/ /home/jovyan/seamless-docker/
RUN chown -R jovyan /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
