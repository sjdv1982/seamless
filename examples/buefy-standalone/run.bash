#!/bin/bash
set -u -e

echo '1. generate initial-graph.seamless, initial-graph.zip'
python3 gen-initial-graph.py

echo '2. generate webform.json (can be edited manually) from Seamless graph'
python3 seamless2webform.py initial-graph.seamless webform.json 'Seamless + buefy example'

echo '3. generate index.html, index.js from webform'
python3 generate-webpage.py webform.json

echo '4. incorporate index.html, index.js, seamless-client.js into the graph'
python3 gen-webgraph.py \
  initial-graph.seamless initial-graph.zip \
  buefy-example.seamless buefy-example.zip

echo 'Done: buefy-example .seamless/.zip generated'