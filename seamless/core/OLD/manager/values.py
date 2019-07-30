import weakref

class ValueManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)


'''
        self.expression_cache = ExpressionCache(self)
        self.value_cache = ValueCache(self)
        self.label_cache = LabelCache(self)
        self.temprefmanager = TempRefManager()
        self.temprefmanager_future = asyncio.ensure_future(self.temprefmanager.loop())

        #integrate with cache_task_manager (create Events for it)
        #NOTE: when an inchannel update is received, the cell checksum will change, 
        #  but outchannel expression result checksums may stay the same!
        #  The structuredcell monitor backend will inform which outchannels have changed!

    def cache_expression(self, expression, buffer):
        """Generates object value cache and semantic key for expression
        Invoke this routine in cache of a partial value cache miss, i.e.
        the buffer checksum is a hit, but the semantic key is either
        unknown or has expired from object cache"""

        semantic_obj, semantic_key = protocol.evaluate_from_buffer(expression, buffer)
        self.value_cache.add_semantic_key(semantic_key, semantic_obj)
        self.expression_cache.expression_to_semantic_key[expression] = semantic_key        
        return semantic_obj, semantic_key


    def get_expression(self, expression):
        if not isinstance(expression, Expression):
            raise TypeError(expression)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(expression)
        cache_hit = False
        if semantic_key is not None:
            semantic_value = self.value_cache.get_object(semantic_key)
            if semantic_value is not None:
                cache_hit = True
        if not cache_hit:
            checksum = expression.buffer_checksum
            buffer_item = self.get_value_from_checksum(checksum)
            is_none = False
            if buffer_item is None:
                is_none = True
            else:
                _, _, buffer = buffer_item
                if buffer is None:
                    is_none = True
            if is_none:
                checksum_hex = checksum.hex() if checksum is not None else None
                raise CacheMissError("Checksum not in value cache", checksum_hex)            
            semantic_value, _ = self.cache_expression(expression, buffer)
        return semantic_value

    def build_expression(self, accessor):
        cell = accessor.cell
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            return None
        return accessor.to_expression(checksum)

    def get_default_accessor(self, cell=None):
        from .cell import Cell, MixedCell
        if cell is None:
            cell = MixedCell
        elif not isinstance(cell, Cell):
            raise TypeError(cell)
        default_accessor = Accessor()
        default_accessor.celltype = cell._celltype
        default_accessor.storage_type = cell._storage_type
        default_accessor.cell = cell
        default_accessor.access_mode = cell._default_access_mode
        default_accessor.content_type = cell._content_type
        return default_accessor

    def cell_semantic_checksum(self, cell, subpath):
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)        
        if checksum is None:
            return None
        accessor = self.get_default_accessor(cell)
        accessor.subpath = subpath
        expression = accessor.to_expression(checksum)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(expression)
        if semantic_key is None:
            buffer_item = self.get_value_from_checksum(checksum)
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            _, semantic_key = self.cache_expression(expression, buffer)
        semantic_checksum, _, _ = semantic_key
        return semantic_checksum  

    def get_checksum_from_label(self, label):
        from ..communionserver import communionserver
        communionserver.wait(self)
        checksum = self.label_cache.get_checksum(label)
        if checksum is None:
            cache_task = self.cache_task_manager.remote_checksum_from_label(label)
            if cache_task is None:
                return None
            cache_task.join()
            checksum = self.label_cache.get_checksum(label)  #  Label will now have been added to cache
        return checksum

    def get_value_from_checksum(self, checksum):
        raise NotImplementedError #livegraph branch
        # Needs a complete overhaul; might be deleted completely, and use only _async (see also manager.py:get_value_from_checksum)
         
        from ..communionserver import communionserver
        communionserver.wait(self)
        if checksum is None:
            return None
        buffer_item = library.value_cache.get_buffer(checksum)
        if buffer_item is None:
            buffer_item = self.value_cache.get_buffer(checksum)
        if buffer_item is None:
            cache_task = self.cache_task_manager.remote_value(checksum)
            if cache_task is None:
                return None
            cache_task.join()
            buffer_item = self.value_cache.get_buffer(checksum)
        return buffer_item
        
    async def get_value_from_checksum_async(self, checksum):
        raise NotImplementedError #livegraph branch
        # Needs a complete overhaul; create an async event, for which get_value_from_checksum could wait

        from ..communionserver import communionserver
        await communionserver.wait_async(self)
        buffer_item = library.value_cache.get_buffer(checksum)
        if buffer_item is None:
            buffer_item = self.value_cache.get_buffer(checksum)        
        if buffer_item is None:
            cache_task = self.cache_task_manager.remote_value(checksum)            
            if cache_task is None:
                return None
            await cache_task.future
            buffer_item = self.value_cache.get_buffer(checksum)
        return buffer_item

'''