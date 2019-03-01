from enum import Enum

class Status:
    StatusDataEnum =  Enum('StatusDataEnum',
        ('OK', 'PENDING', 'UNDEFINED', 'UPSTREAM_ERROR', 'INVALID', 'UNCONNECTED')
    )
    # "UNCONNECTED" is only for workers
    # "INVALID" means parsing error or schema violation (with error message) (cell only)
    # "UPSTREAM_ERROR" means 'INVALID', 'UNDEFINED' or 'UNCONNECTED' upstream
    StatusExecEnum =  Enum('StatusExecEnum',
        ('FINISHED', 'EXECUTING', 'READY', 'PENDING', 'BLOCKED', 'ERROR')
    ) # "BLOCKED" means essentially "something in the data prevents me from running"
      # "ERROR" means an error in execution (with error message)
      # "EXECUTING" and "READY" are only for transformers, since macros and reactors execute immediately
    StatusAuthEnum = Enum('StatusAuthEnum',
        ("FRESH", "PRELIMINARY", "OVERRULED", "OBSOLETE")
    )
    data_status = None  # in case of workers, the result of dependency propagation
    auth_status = None  # in case of workers, the result of dependency propagation
    exec_status = None  # only for workers: the result of execution
    live_status = False # only for reactors; means that there is a live namespace
    _overruled = False
    _unconnected_list = []
    def __init__(self, type):
        assert type in ("cell", "transformer", "macro", "reactor")
        self._type = type
        if type == "cell":
            self.data_status = self.StatusDataEnum.UNDEFINED
        else:
            self.data_status = self.StatusDataEnum.UNCONNECTED
            self.exec_status = self.StatusExecEnum.BLOCKED
        self.auth_status = self.StatusAuthEnum.FRESH

    def _str_cell(self):
        dstatus = self.data
        if dstatus == "UNDEFINED":
            return dstatus
        else:
            astatus = self.auth
            if astatus == "FRESH":
                return dstatus
            elif dstatus == "OK":
                return astatus
            else:
                return dstatus + "," + astatus

    def _str_transformer(self):
        dstatus = str(self.data)
        estatus = str(self.exec)
        astatus = str(self.auth)
        if dstatus == "UNCONNECTED":
            result = dstatus 
            if len(self._unconnected_list):
                result += ": " + ",".join(self._unconnected_list) 
            return result
        elif estatus == "BLOCKED":
            result = self._str_cell()
            if result == "UNDEFINED":
                return "BLOCKED"
            else:
                return "BLOCKED,"+result
        elif dstatus == "PENDING":
            assert estatus in ("PENDING", "READY", "EXECUTING"), estatus
            if astatus == "FRESH":
                return estatus
            else:
                return estatus + "," + astatus
        else:
            assert dstatus == "OK" or estatus == "ERROR", (dstatus, estatus)
            astatus = self.auth
            if astatus == "FRESH":
                return estatus
            elif estatus == "FINISHED":
                return astatus
            else:
                return estatus + "," + astatus

    def _str_reactor(self):
        dstatus = str(self.data)
        estatus = str(self.exec)
        astatus = str(self.auth)
        live = self.live_status
        if dstatus == "UNCONNECTED":
            return dstatus
        elif estatus == "BLOCKED":
            result0 = self._str_cell()
            if result0 == "UNDEFINED":
                result = "BLOCKED"
            else:
                result = "BLOCKED,"+result0
        elif dstatus == "PENDING":
            assert estatus == "PENDING", estatus
            if astatus == "FRESH":
                result = estatus
            else:
                result = estatus + "," + astatus
        else:
            assert dstatus == "OK" or estatus == "ERROR", (dstatus, estatus)
            astatus = self.auth
            if astatus == "FRESH":
                result = estatus
            elif estatus == "FINISHED":
                result = astatus
            else:
                result = estatus + "," + astatus
        if live:
            result += ",LIVE"
        return result

    def _str_macro(self):
        dstatus = str(self.data)
        estatus = str(self.exec)
        astatus = str(self.auth)
        if dstatus == "UNCONNECTED":
            return dstatus
        elif estatus == "BLOCKED":
            result = self._str_cell()
            if result == "UNDEFINED":
                return "BLOCKED"
            else:
                return "BLOCKED,"+result
        elif dstatus == "PENDING":
            assert estatus == "PENDING", estatus
            if astatus == "FRESH":
                return estatus
            else:
                return estatus + "," + astatus
        else:
            assert dstatus == "OK" or estatus == "ERROR", (dstatus, estatus)
            astatus = self.auth
            if astatus == "FRESH":
                return estatus
            elif estatus == "FINISHED":
                return astatus
            else:
                return estatus + "," + astatus


    def __str__(self):
        if self._type == "cell":
            return self._str_cell()
        elif self._type == "transformer":
            return self._str_transformer()
        elif self._type == "macro":
            return self._str_macro()
        elif self._type == "reactor":
            return self._str_reactor()
        else:
            raise TypeError(self._type)

    @property
    def data(self):
        return self.data_status.name

    @data.setter
    def data(self, value):
        if isinstance(value, str):
            value = getattr(self.StatusDataEnum, value.upper())
        if not isinstance(value, self.StatusDataEnum):
            raise TypeError
        self.data_status = value

    @property
    def exec(self):
        return self.exec_status.name

    @exec.setter
    def exec(self, value):
        if isinstance(value, str):
            value = getattr(self.StatusExecEnum, value.upper())
        if not isinstance(value, self.StatusExecEnum):
            raise TypeError
        self.exec_status = value

    @property
    def auth(self):
        return self.auth_status.name

    @auth.setter
    def auth(self, value):
        if isinstance(value, str):
            value = getattr(self.StatusAuthEnum, value.upper())
        if not isinstance(value, self.StatusAuthEnum):
            raise TypeError
        self.auth_status = value

    def __eq__(self, other):
        return str(self) == str(other)

    def is_different(self, other):
        assert isinstance(other, Status)
        return (self.data_status != other.data_status) or \
            (self.exec_status != other.exec_status) or \
            (self.auth_status != other.auth_status)

