import weakref

from .redis_client import redis_sinks, redis_caches

def validate_label(label):
    assert isinstance(label, str)
    assert len(label) < 80

label_caches = weakref.WeakSet()

class LabelCache:
    """Label => checksum cache.
    Label are strings and can be up to 80 characters    
    Every label must be unique, i.e. can point to only one checksum, and vice versa
    Ephemeral, will never be cleared, but a label may be re-defined
    """
    def __init__(self, manager):
        label_caches.add(self)
        self.manager = weakref.ref(manager)
        self._label_to_checksum = {}
        self._checksum_to_label = {}

    def set(self, label, checksum):
        old_checksum = self._label_to_checksum.pop(label, None)
        if old_checksum is not None:
            old_label = self._checksum_to_label.pop(old_checksum)
            assert old_label == label
        old_label = self._checksum_to_label.pop(checksum, None)
        if old_label is not None:
            old_checksum = self._label_to_checksum.pop(old_label)
            assert old_checksum == checksum
        self._label_to_checksum[label] = checksum
        self._checksum_to_label[checksum] = label      
        redis_sinks.set_label(label, checksum)

    def get_label(self, checksum):
        return self._checksum_to_label.get(checksum)      

    def get_checksum(self, label):
        result = self._label_to_checksum.get(label)
        if result is not None:
            return result
        return redis_caches.get_label(label)
