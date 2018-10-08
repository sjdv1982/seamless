from threading import RLock
from weakref import WeakValueDictionary

locks = WeakValueDictionary()
locklock = RLock() #lock to modify the locks, or to change sys.path
