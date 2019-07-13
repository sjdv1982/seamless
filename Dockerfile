FROM jupyter/scipy-notebook:latest
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
COPY requirements.txt requirements.txt
COPY seamless/ /home/jovyan/software/seamless
COPY tests/ /home/jovyan/seamless-tests/
RUN pip install -r requirements.txt
RUN chown -R jovyan /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
