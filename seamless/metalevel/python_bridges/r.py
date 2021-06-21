"""
# Adapted by Sjoerd de Vries
# from https://github.com/rpy2/rpy2/blob/master/rpy2/ipython/rmagic.py 

# Original license:

# -----------------------------------------------------------------------------
#  Copyright (C) 2012 The IPython Development Team
#  Copyright (C) 2013-2019 rpy2 authors
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
# -----------------------------------------------------------------------------
"""

def bridge_r(*, bridge_parameters, **kwargs):
    import shutil
    from copy import deepcopy

    device = bridge_parameters["device"]
    Rstdout_cache = []

    def write_stdout(output):
        Rstdout_cache.append(output)

    import textwrap
    import numpy as np
    import tempfile
    from glob import glob
    from os import stat
    import contextlib

    import rpy2
    import rpy2.rinterface as ri
    import rpy2.robjects as ro
    from rpy2.robjects.lib import grdevices
    import rpy2.robjects.packages as rpacks
    from rpy2.robjects.conversion import (Converter,
                                        localconverter)
    from rpy2.robjects.conversion import converter as template_converter
    from rpy2.robjects import numpy2ri
    template_converter += numpy2ri.converter
    
    class RInterpreterError(ri.embedded.RRuntimeError):
        """An error when running R code in Seamless."""

        msg_prefix_template = ('Failed to parse and evaluate line %r.\n'
                            'R error message: %r')
        rstdout_prefix = '\nR stdout:\n'

        def __init__(self, line, err, stdout):
            self.line = line
            self.err = err.rstrip()
            self.stdout = stdout.rstrip()

        def __str__(self):
            s = (self.msg_prefix_template %
                (self.line, self.err))
            if self.stdout and (self.stdout != self.err):
                s += self.rstdout_prefix + self.stdout
            return s

    converter = Converter('Seamless conversion',
                      template=template_converter)

    @converter.rpy2py.register(ri.SexpVector)
    def _(obj):
        print("CONV1")
        if len(obj) == 1:
            obj = obj[0]
        return obj
    
    @converter.rpy2py.register(ro.vectors.StrVector)
    def _(obj):
        return str(obj[0])                      

    try:
        cairo = rpacks.importr('Cairo')
    except ri.embedded.RRuntimeError as rre:
        if rpacks.isinstalled('Cairo'):
            msg = ('An error occurred when trying to load the ' +
                    'R package Cairo\'\n%s' % str(rre))
        else:
            msg = textwrap.dedent("""
            The R package 'Cairo' is required but it does not appear
            to be installed/available
            """)
        raise RInterpreterError(msg)


    def setup_graphics(args):
        """Setup graphics in preparation for evaluating R code.
        args : argparse bunch (should be whatever the R magic got)."""

        args = deepcopy(args)
        if args.get('units') is not None:
            if args["units"] != "px" and getattr(args, "res") is None:
                args.res = 72

        plot_arg_names = ['width', 'height', 'pointsize', 'bg']
        if device == 'png':
            plot_arg_names += ['units', 'res']

        argdict = {}
        for name in plot_arg_names:
            val = args.get(name)
            if val is not None:
                argdict[name] = val

        graph_dir = None
        if device in ['png', 'svg']:
            # Create a temporary directory for R graphics output
            # TODO: Do we want to capture file output for other device types
            # other than svg & png?
            graph_dir = tempfile.mkdtemp()
            graph_dir_fix_slashes = graph_dir.replace('\\', '/')

            if device == 'png':
                # Note: that %% is to pass into R for interpolation there
                grdevices.png("%s/Rplots%%03d.png" % graph_dir_fix_slashes,
                              **argdict)
            elif device == 'svg':
                argdict.pop("width")  # BUG in Cairo or rpy2?
                argdict.pop("height") # BUG in Cairo or rpy2?
                cairo.CairoSVG("%s/Rplot.svg" % graph_dir_fix_slashes,
                                    **argdict)
        else:
            # TODO: This isn't actually an R interpreter error...
            raise ValueError(
                'device must be one of ("png", "svg")')
        return graph_dir

    def get_graphics(graph_dir):
        images = []

        if device == 'png':
            for imgfile in sorted(glob('%s/Rplots*png' % graph_dir)):
                if stat(imgfile).st_size >= 1000:
                    with open(imgfile, 'rb') as fh_img:
                        images.append(fh_img.read())
        else:
            # as onefile=TRUE, there is only one .svg file
            imgfile = "%s/Rplot.svg" % graph_dir
            # Cairo creates an SVG file every time R is called
            # -- empty ones are not published
            if stat(imgfile).st_size >= 1000:
                with open(imgfile, 'rb') as fh_img:
                    images.append(fh_img.read().decode())

        return images

    def evalR(code):
        Rstdout_cache[:] = []
        cache_display_data = bridge_parameters["cache_display_data"]
        with contextlib.ExitStack() as stack:
            if cache_display_data:
                stack.enter(
                    rpy2.rinterface_lib
                    .callbacks.obj_in_module(rpy2.rinterface_lib.callbacks,
                                             'consolewrite_print',
                                             write_stdout)
                )
            try:
                # Need the newline in case the last line in code is a comment.
                ro.r("withVisible({%s\n})" % code)
            except (ri.embedded.RRuntimeError, ValueError) as exception:
                # Otherwise next return seems to have copy of error.
                warning_or_other_msg = ''.join(Rstdout_cache)
                raise RInterpreterError(code, str(exception),
                                        warning_or_other_msg)
            text_output = ''.join(Rstdout_cache)
            if len(text_output):
                print(text_output)

    # Transfer input
    with localconverter(converter) as cv:
        ro.r.assign("BLAH", [1,2,3])
        for pin in PINS:
            if pin in ("code", "bridge_parameters"):
                continue
            print("INP", pin)
            try: 
                ro.r.assign(pin, PINS[pin])
            except NotImplementedError as exc:
                raise NotImplementedError("Pin '{}':".format(pin)+str(exc.args))
    
    # Prepare graphics

    try:
        graph_dir = setup_graphics(bridge_parameters)
        device_off = False

        # Run code
        with localconverter(converter) as cv:
            code = PINS["code"]
            evalR(code)
            if device in ['png', 'svg']:
                ro.r('dev.off()')        
            device_off = True            
            images = get_graphics(graph_dir)
            try:
                result = ro.globalenv.find("result")
            except KeyError:
                result = None
            else:
                result = ro.conversion.rpy2py(result)
            if result is not None and len(images):
                raise ValueError("R transformer contains a result AND plots")
            elif result is None and not len(images):
                raise ValueError("R transformer contains neither result nor plots")
            elif len(images):
                if len(images) > 1:
                    raise ValueError("R transformer returns multiple plots, not supported")
                result = images[0]
            else:
                pass
        return result
    finally:
        if not device_off:
            if device in ['png', 'svg']:
                ro.r('dev.off()')        
        shutil.rmtree(graph_dir)

default_bridge_parameters = {
    "device": "svg",
    "cache_display_data": False,
    "width": 640, 
    "height": 480,
    "pointsize": 12,
    'bg': 'white',
    'units': 'px',
    'res': 72

}
 