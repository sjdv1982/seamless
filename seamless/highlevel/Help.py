class ContextHelpMixin:
    _help_path = ("HELP",)
    _help_path_index = ("HELP", "index")

    @property
    def help(self):
        try:
            help = self._get_path(self._help_path)
        except AttributeError:
            help = """This toplevel context does not have any help or documentation.
To create some help:
- Assign a text to the .help attribute
or:
- Call the .create_help method"""
        return help    
    
    @help.setter
    def help(self, newhelp):
        from .Context import Context 
        help = self.help
        if isinstance(help, (str, Context)):
            if not isinstance(newhelp, str):
                raise TypeError("You can set new help only to a string")
            helpcell = Cell("text")
            helpcell.set(newhelp)
            assign(self, self._help_path, helpcell)
            try:
                verify_sync_translate()
                self.translate()
            except RuntimeError:
                self._translate()
        elif isinstance(help, Cell):
            help.set(newhelp)

    def create_help(self, mode=None, force=False):
        """Creates a help cell or help context"""
        allowed = ("context", "text", "markdown", "html")
        # TODO: html -> share
        if mode not in allowed:
            raise ValueError("'mode' must be one of: {}".format(allowed))
        help = self.help
        if isinstance(help, Cell):
            if mode == "context":
                helpcelltype = help.celltype
                helpmimetype = help.mimetype              
                helpvalue = help._get_hcell().get("TEMP")
                if helpvalue is None:
                    helpvalue = help.value
                self._destroy_path(self._help_path)
                self._graph.nodes[self._help_path] = {
                    "path": self._help_path,
                    "type": "context"
                }
                if helpvalue is not None:
                    print("Help cell already exists. Expanding it to a context..")
                helpcell = Cell(helpcelltype)
                # TODO: html -> share
                helpcell.mimetype = helpmimetype
                helpcell.set(helpvalue)
                assign(self, self._help_path_index, helpcell)
                try:
                    verify_sync_translate()
                    self.translate()
                except RuntimeError:
                    self._translate()
                    

    def _get_doc(self):  
        from .Context import Context
        help = self.help
        if isinstance(help, str):
            return help
        if isinstance(help, Context):
            try:
                help = self._get_path(self._help_path_index)
            except AttributeError:
                return """This toplevel context has a help context, but no index
To create some help:
- Assign a text to the .help attribute
or:
- Assign help.index to a new Cell"""
        helpvalue = help._get_hcell().get("TEMP")
        if helpvalue is None:
            helpvalue = help.value
        if helpvalue is None:
            return "This toplevel context has a help cell, but it is empty"
        return helpvalue

from .Cell import Cell
from .assign import assign
from .. import verify_sync_translate   
