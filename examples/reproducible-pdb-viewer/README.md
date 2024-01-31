# Reproducible molecular viewer

## Run via Jupyter

To run this example, open the project notebook (`reproducible-pdb-viewer.ipynb`) inside Jupyter.
Jupyter can be launched inside a Seamless Docker container with the `seamless-jupyter` command.

After running all the cells, open http://localhost:5813

## Run standalone

It is also possible to run this example independent of Jupyter. This requires the following steps:

1. Export the Seamless workflow from the notebook. **This has already been done**.
To do it again (e.g. after modification), execute the following code at the end of the notebook:
```python
os.makedirs("export", exist_ok=True)
ctx.save_graph("export/reproducible-pdb-viewer.seamless")
ctx.save_zip("export/reproducible-pdb-viewer.zip")
webctx.save_graph("export/reproducible-pdb-viewer-webctx.seamless")
webctx.save_zip("export/reproducible-pdb-viewer-webctx.zip")
```

2. Exit the notebook and Jupyter, i.e. stop the `seamless-jupyter` command.

3. Launch the standalone PDB viewer with the following command:
```bash
seamless-serve-graph \
    export/reproducible-pdb-viewer.seamless \
    --load-zip export/reproducible-pdb-viewer.zip \
    --status-graph export/reproducible-pdb-viewer-webctx.seamless \
    --load-zip export/reproducible-pdb-viewer-webctx.zip \
     --delegate 1 \
     --buffer-server https://buffer.rpbs.univ-paris-diderot.fr \
     --fair-server https://fair.rpbs.univ-paris-diderot.fr
```

4. Open http://localhost:5813