# syntax=docker/dockerfile:1

FROM rpbs/seamless:0.11
USER root
#RUN --mount=from=seamless cp seamless/communion_client.py seamless/communion_server.py /opt/conda/lib/python3.8/site-packages/seamless && \
#    cp seamless/core/transformation.py /opt/conda/lib/python3.8/site-packages/seamless/core/transformation.py && \
#    cp seamless/highlevel/assign.py  /opt/conda/lib/python3.8/site-packages/seamless/highlevel/assign.py
#COPY --from=seamless-tools scripts/serve-graph.py /home/jovyan/seamless-scripts
RUN sed -i 's/3.10.9/3.10.*/' /opt/conda/conda-meta/pinned
