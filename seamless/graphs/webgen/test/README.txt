In terminal 1:
python3 gen-initial-graph.py
ipython3 -i test.py

In terminal 2:
ipython3 -i gen-initial-graph.py

- Open http://localhost:5813/index.html
- In terminal 2, add and remove new cells, and run save()
- In terminal 1, modify cell values in ctx_original
- Open and modify webform.json and webform-CONFLICT.json
- Open and modify index.html/.js and index-CONFLICT.html/.js

Cleanup:
rm -f initial-graph.zip initial-webform.json initial-graph.seamless webform.json webform-CONFLICT.txt
rm -f index.html index.js index-CONFLICT.js index-CONFLICT.html