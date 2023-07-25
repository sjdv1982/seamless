from .manager import Manager

def block():
    from ..cache.transformation_cache import transformation_cache
    from ..macro_mode import _toplevel_managers
    from .tasks import UnblockedTasks
    Manager._blocked = True
    for manager in _toplevel_managers:
        taskmanager = manager.taskmanager
        for task in list(taskmanager.tasks):
            if not isinstance(task, UnblockedTasks):
                taskmanager.cancel_task(task)
        taskmanager.launching_tasks.clear()
    transformation_cache._blocked = True
    for transformer in transformation_cache.transformer_to_transformations:
        transformation_cache.cancel_transformer(transformer, void_error=False)

def unblock():
    from ..cache.transformation_cache import transformation_cache
    Manager._blocked = False
    transformation_cache._blocked = False