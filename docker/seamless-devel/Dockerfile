FROM rpbs/seamless-deps
LABEL author="Sjoerd de Vries <sjoerd.de-vries@inserm.fr>"
USER root
RUN mkdir /home/jovyan/software && \
    ln -s /seamless/seamless /home/jovyan/software/seamless && \
    ln -s /seamless/tests /home/jovyan/seamless-tests && \
    ln -s /seamless/examples /home/jovyan/seamless-examples && \
    ln -s /seamless/docker/commands /home/jovyan/seamless-docker && \
    ln -s /seamless/scripts /home/jovyan/seamless-scripts && \
    ln -s /seamless/tools /home/jovyan/seamless-tools
RUN chown -R jovyan /home/jovyan && chmod -R g=u /home/jovyan
ENV PYTHONPATH /home/jovyan/software:$PYTHONPATH
