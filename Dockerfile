FROM jupyter/scipy-notebook:latest
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
COPY seamless/ /home/jovyan/software/seamless
COPY tests/ /home/jovyan/seamless-tests/
RUN pip install cson websockets aiohttp aiohttp_cors wurlitzer nest_asyncio redis docker jsonschema==3.0.0a3
RUN chown -R jovyan /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
