from .. import datatypes
import traceback, inspect, ast

class Cell:
    _datatype = None
    _data = None #data, always in text format
    _status = "uninitialized" #TODO: more sophisticated than a simple string
    _exception = None         #TODO: more sophisticated than a simple string

    _name = None
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self, value):
        self._name = value

    def __init__(self, datatype):
        assert datatypes.check_registered(datatype)
        self._datatype = datatype
    def set(self, text_or_object):
        """This method is used to update cell data from Python code
        in the main thread"""
        if isinstance(text_or_object, (str, bytes)):
            self._text_set(text_or_object, from_update = False)
        else:
            self._object_set(text_or_object, from_update = False)
    def _text_set(self, data, from_update):
        try:
            """Check if we can parse the text"""
            datatypes.parse(self._datatype, data, from_update=from_update)
        except datatypes.ParseError:
            self._status = "error"
            self._exception = traceback.format_exc()
            if not from_update:
                raise
        else:
            self._data = data
            self._status = "OK"
    def _object_set(self, object_, from_update):
        try:
            """
            Construct the object:
             If the object is already of the correct type,
               then constructed_object is object_
             Some datatypes (i.e. Spyder) can construct the object from
              heterogenous input
            """
            constructed_object = datatypes.construct(self._datatype, object_)
        except datatypes.ConstructionError:
            self._status = "error"
            self._exception = traceback.format_exc()
            if not from_update:
                raise
        else:
            data = datatypes.serialize(self._datatype, object_) #Normally no error here...
            self._data = data
            self._status = "OK"
    def _update(self, data):
        """This method is invoked when cell data is updated by controllers"""
        self._text_set(data, from_update = True)
    @property
    def datatype(self):
        return self._datatype
    @property
    def data(self):
        return self._data
    @property
    def status(self):
        return self._status
    @property
    def exception(self):
        return self._exception
    def _on_connect(self, controller):
        pass
    def _on_disconnect(self, controller):
        pass

class PythonCell(Cell):
    """
    Python cells may contain either a code block or a function
    Controllers that are connected to it may require either a code block or a
     function
    Mismatch between the two is not a problem, unless:
          Connected controllers have conflicting requirements
        OR
            A function is required (typically, true for transformers)
          AND
            The cell contains a code block
          AND
            The code block contains no return statement
    """
    _datatype = ("text", "python")
    _requires_function = None
    _is_function = None
    _connections = 0
    def _text_set(self, data, from_update):
        try:
            """Check if the code is valid Python syntax"""
            astree = compile(data, self._name, "exec", ast.PyCF_ONLY_AST)
        except SyntaxError:
            if not from_update:
                raise
            else:
                self._status = "error"
                self._exception = traceback.format_exc()
        else:
            """
            Check if we are compiling a function or not
            If not (= code block), and a function is required,
             then the code block must contain return statement(s)
            """
            is_function  = (len(astree.body) == 1 and \
              isinstance(a.body[0], ast.FunctionDef))
            ok = True
            if not is_function and self._requires_function:
                ok = False
                try:
                    compile(data, self._name, "exec")
                except SyntaxError as exc:
                    if exc.args[0] == "'return' outside function":
                        ok = True
            if ok:
                self._is_function = is_function
                self._data = data
                self._status = "OK"
            else:
                exc = SyntaxError("Block must contain return statement(s)")
                if not from_update:
                    raise exc
                else:
                    self._status = "error"
                    self._exception = exc

    def _object_set(self, object_, from_update):
        try:
            """
            Try to retrieve the source code
            Will only work if code is a function
            """
            if not inspect.isfunction(object_):
                raise Exception("Python object must be a function")
            code = inspect.getsource(object_)
        except:
            self._status = "error"
            self._exception = traceback.format_exc()
            if not from_update:
                raise
        else:
            self._is_function = True
            self._data = code
            self._status = "OK"

    def _on_connect(self, controller):
        if self._requires_function == False and \
          controller._requires_function == True:
            raise Exception(
                """Cannot connect to %s: controller requires a code function
                 whereas other connected controllers require a code block""" \
                 % type(controller)
            )
        elif self._requires_function == True and \
          controller._requires_function == False:
            raise Exception(
                """Cannot connect to %s: controller requires a code block
                 whereas other connected controllers require a function""" \
                 % type(controller)
            )

        self._requires_function = controller._requires_function
        self._connections += 1

    def _on_disconnect(self, controller):
        self._connections -= 1
        if self._connections == 0:
            self._requires_function = None


_handlers = {
    ("text", "code", "python"): PythonCell
}

def cell(datatype, text_or_object = None):
    cellclass = Cell
    if datatype in _handlers:
        cellclass = _handlers[datatype]
    newcell = cellclass(datatype)
    if text_or_object is not None:
        newcell.set(text_or_object)
    return newcell

def pythoncell(text_or_object = None):
    return cell(("text", "code", "python"), text_or_object)
