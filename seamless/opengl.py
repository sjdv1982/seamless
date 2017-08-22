## GL related stuff... put this into its own file as soon as the API is stable
_opengl_contexts = []
_opengl_destructors = {}
def add_opengl_context(context):
    assert context not in _opengl_contexts
    _opengl_contexts.append(context)
    _opengl_destructors[context] = []

_removing_context = None
def remove_opengl_context(context):
    global _removing_context
    old_removing_context = _removing_context
    try:
        _removing_context = True
        #print("REMOVE OPENGL CONTEXT", context, context in _opengl_contexts)
        if context in _opengl_contexts:
            _opengl_contexts.remove(context)
            for destructor in _opengl_destructors[context]:
                destructor()
            _opengl_destructors.pop(context)
        #print("/REMOVE OPENGL CONTEXT", context)
    finally:
        _removing_context = old_removing_context

def add_opengl_destructor(context, destructor):
    assert context in _opengl_destructors
    assert callable(destructor)
    if destructor not in _opengl_destructors[context]:
        _opengl_destructors[context].append(destructor)

_opengl_active = False
_opengl_active_context = None
def activate_opengl():
    global _opengl_active, _opengl_active_context
    from PyQt5.QtGui import QOpenGLContext
    assert not _opengl_active
    _opengl_active_context = QOpenGLContext.currentContext()
    _opengl_active = True

def deactivate_opengl():
    global _opengl_active, _opengl_active_context
    _opengl_active_context = None
    _opengl_active = False

def has_opengl():
    from . import qt_error
    return qt_error is None and _opengl_active

def opengl_current_context():
    if not _opengl_active:
        return None
    if _removing_context is not None:
        return None
    from PyQt5.QtGui import QOpenGLContext
    curr = QOpenGLContext.currentContext()
    if curr is not _opengl_active_context:
        raise Exception("Qt changed OpenGL context while activated")
    return curr
