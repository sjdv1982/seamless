This example has no notebook. The workflow graph
(grid-editor.seamless and grid-editor.zip) was built
by running the build-workflow-graph script, this has already been done.

To serve the workflow graph, run the following command:

seamless-serve-graph-interactive grid-editor.seamless --load-zip grid-editor.zip --mounts

or:

seamless-serve-graph-interactive \\
    /home/jovyan/seamless-examples/grid-editor-example/grid-editor.seamless \\
    --load-zip /home/jovyan/seamless-examples/grid-editor-example/grid-editor.zip \\
    --mounts

Then, open the web interface: http://localhost:5813/ctx/grid-editor.html

The workflow comes from a bioinformatics project. 
Originally, the goal is to superimpose two protein molecules
that are represented by discrete grids.

In the browser, you can click on the grids to fill or empty a square.
You can also do this by editing the files grid_data1.txt and grid_data2.txt.
They are in live sync with the web interface.

You can also edit the x and y translation of the second grid, 
either in the web interface, or in translation.json.

seamless-serve-graph-interactive opens the workflow in an IPython shell,
where you can set the cell values programmatically, or do ctx.status to
detect errors.
If you don't want an IPython shell, use seamless-serve-graph instead.

Finally, you can also edit the web interface itself (grid-editor.html/css/js).
Some web interface parameters can be edited in grid_params.json.
Like everything else in Seamless, you can edit while the workflow keeps
running; just save the file and refresh your browser.


