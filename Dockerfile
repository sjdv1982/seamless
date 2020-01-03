FROM jupyter/scipy-notebook:4b0e7c708aa5
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY seamless/ /home/jovyan/software/seamless
COPY tests/ /home/jovyan/seamless-tests/
RUN chown -R jovyan /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
