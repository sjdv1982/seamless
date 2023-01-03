# Interactive collaborative web server

To run this example, open the project notebook (`webserver-example.ipynb`).

For this example, an empty Seamless project was generated using `seamless-new-project webserver-example`.

To the empty project notebook, a simple workflow has been added. First, a version that does not use Seamless, in three parts. Then, the Seamless version, with the same three parts.

The workflow is minimalist, but shows a combination of Python and command line tools, as is typical in bioinformatics.

In this example, typically only the final result is shown. In contrast, the `webserver-demo` gives a more step-by-step explanation on how to convert an existing workflow to Seamless.

The web interface was customized by modifying `web/webform.json`, see `web/webform-AUTOGEN.json` for the unmodified file. Finally, `web/index.html` was edited directly, removing "lazy" from the "markerline" input. See `web/index-AUTOGEN.html` for the unmodified file.