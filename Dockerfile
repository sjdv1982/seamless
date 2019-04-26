FROM jupyter/scipy-notebook:latest
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
LABEL version="0.2"
USER root
#COPY setup.py setup.py
#COPY seamless/ seamless/
COPY seamless/ /home/jovyan/software/seamless
COPY tests/ /home/jovyan/seamless-tests/
#RUN pip install aiohttp && python3 setup.py install
RUN pip install cson websockets aiohttp aiohttp_cors wurlitzer nest_asyncio redis docker
RUN chown -R jovyan /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
