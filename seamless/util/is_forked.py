"""Front for workflow.util.is_forked.
Returns False is seamless.workflow has not been imported."""

import seamless


def _is_forked():
    from seamless.workflow.util import is_forked as workflow_is_forked

    return workflow_is_forked()


def is_forked():
    """Front for workflow.util.is_forked.
    Returns False is seamless.workflow has not been imported."""
    if not seamless.SEAMLESS_WORKFLOW_IMPORTED:
        return False
    return _is_forked()
