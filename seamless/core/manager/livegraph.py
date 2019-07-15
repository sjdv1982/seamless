#TODO: overhaul, and a lot of this goes to status.py

"""
        self.cell_cache = CellCache(self)
        self.accessor_cache = AccessorCache(self)
        self.transform_cache = TransformCache(self)
        
        self.reactors = WeakKeyDictionary() # RuntimeReactors
        self.cell_to_cell = [] # list of (source-accessor-or-pathtuple, target-accessor-or-pathtuple); pathtuples are (Path, subpath)
        ###self._processed_accessors = {} # to prevent cycles in propagation ### SHOULD NOT BE NEEDED

    def set_reactor_result(self, rtreactor, pinname, value):
        print("TODO: Manager.set_reactor_result: expand code properly, see evaluate.py")
        reactor = rtreactor.reactor()
        if pinname in rtreactor.output_dict:
            cells = rtreactor.output_dict[pinname]
        elif pinname in rtreactor.edit_dict:
            cells = [rtreactor.edit_dict[pinname]]
        else:
            raise ValueError(pinname)
        for cell, subpath in cells:
            status = self.status[cell][subpath]
            status.auth = "FRESH"
            self.set_cell(cell, value, origin=reactor, subpath=subpath)
        self.schedule_jobs()

    def set_reactor_exception(self, rtreactor, codename, exception):
        # TODO: store exception? log it?
        reactor = rtreactor.reactor()
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s:\n" + exc
        stars = "*" * 60 + "\n"
        print(stars + (msg % (str(reactor)+":"+codename)) + stars, file=sys.stderr)

    def set_macro_exception(self, macro, exception):
        # TODO: store exception? log it?
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s:\n"% str(macro) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)


    def _schedule_transformer(self, transformer):
        debug = transformer.debug
        tcache = self.transform_cache
        old_level1 = self._temp_tf_level1.get(transformer)
        if old_level1 is None:
            old_level1 = tcache.transformer_to_level1.get(transformer)
        new_level1 = tcache.build_level1(transformer)
        if old_level1 != new_level1:
            if old_level1 is not None:
                self.scheduled.append(("transformer", old_level1, False, None))
            self._temp_tf_level1[transformer] = new_level1
            tcache.set_level1(transformer, new_level1)
        self.scheduled.append(("transformer", new_level1, True, debug))

    def _unschedule_transformer(self, transformer):
        tcache = self.transform_cache
        old_level1 = self._temp_tf_level1.get(transformer)
        if old_level1 is None:
            old_level1 = tcache.transformer_to_level1.get(transformer)
        if old_level1 is not None:
            self.scheduled.append(("transformer", old_level1, False, None))
            self._temp_tf_level1[transformer] = None

    def _resolve_propagations(self, propagations):
        curr_propagations = propagations    
        self._processed_accessors.clear()    
        while len(curr_propagations):
            new_propagations = []
            for propagation in curr_propagations:
                assert callable(propagation), propagation
                result = propagation()
                if result is None:
                    continue
                if not isinstance(result, list):
                    raise Exception(propagation, result)
                new_propagations += result
            curr_propagations = new_propagations

    def _propagate_status(self, cell, data_status, auth_status, full, *, cell_subpath, origin=None):
        # "full" indicates a value change, but it is just propagated to update_worker
        # print("propagate status", cell, cell_subpath, data_status, auth_status, full)        
        propagations = []
        from .reactor import Reactor
        from .macro import Path
        if isinstance(cell, Path):
            cell = cell._cell
            if cell is None:
                return
        if cell._celltype == "structured": 
            raise TypeError
        if not hasattr(cell, "_monitor") or cell._monitor is None:
            if cell_subpath == ():
                cell_subpath = None            
            if cell_subpath is not None:
                raise Exception(cell_subpath)
        try:
            status = self.status[cell][cell_subpath]
        except KeyError: #KLUDGE
            if cell_subpath == ():
                cell_subpath = None
                status = self.status[cell][cell_subpath]
        new_data_status = status.data
        new_auth_status = status.auth
        if data_status is not None:
            dstatus = status.data            
            if data_status == "PENDING":
                if str(dstatus) in ("UNDEFINED", "UPSTREAM_ERROR"):
                    new_data_status = "PENDING"
            elif data_status == "UPSTREAM_ERROR":              
                if dstatus == "PENDING":
                    new_data_status = "UPSTREAM_ERROR"
        if auth_status is not None:
            new_auth_status = auth_status
        status.data = new_data_status
        status.auth = new_auth_status        

        if full or new_auth_status is not None or new_data_status is not None:            
            acache = self.accessor_cache
            accessors = itertools.chain(
                self.cell_cache.cell_to_accessors[cell][cell_subpath],
                [self.get_default_accessor(cell)],
            )            
            for accessor in accessors:
                haccessor = hash(accessor)
                for worker, acc in acache.haccessor_to_workers.get(haccessor, []):                    
                    if acc is None:
                        acc = accessor
                    else:
                        if acc.cell is not cell:
                            continue
                    if full and isinstance(worker, Reactor):
                        rtreactor = self.reactors[worker]
                        for pinname, accessor2 in rtreactor.input_dict.items():
                            if accessor2.cell is cell:
                                rtreactor.updated.add(pinname)
                    self.update_worker_status(worker, full)
            propagation = partial(self.update_cell_to_cells,
              cell, data_status, auth_status, 
              full=full, origin=origin,subpath=cell_subpath
            )
            propagations.append(propagation)
            if full:
                upstream = None
                upstream0 = self.cell_cache.cell_from_upstream.get(cell)
                if upstream0 is not None:
                    upstream = upstream0.get(cell_subpath)
                if isinstance(upstream, list):
                    for editpin in upstream:
                        reactor = editpin.worker_ref()
                        assert isinstance(reactor, Reactor)
                        if reactor is origin:
                            continue
                        rtreactor = self.reactors[reactor]
                        rtreactor.updated.add(editpin.name)
                        propagation = partial(
                            self.update_reactor_status, reactor, full=True
                        )
                        propagations.append(propagation)
        return propagations

    def update_transformer_status(self, transformer, full, new_connection=False):
        if transformer._destroyed: return ### TODO, shouldn't happen...
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        if full:
            level1 = tcache.transformer_to_level1.pop(transformer, None)
            if level1 is not None:
                tcache.decref(level1)
        old_status = self.status[transformer]
        new_status = Status("transformer")
        new_status.data, new_status.exec, new_status.auth = "OK", "READY", "FRESH"
        if old_status is not None and old_status.exec == "FINISHED" and not full:
            new_status.exec = "FINISHED"
        unconnected_list = []
        for pin in transformer._pins:
            if transformer._pins[pin].io == "output":
                continue
            if pin not in accessor_dict:
                new_status.data = "UNCONNECTED"
                unconnected_list.append(pin)
                continue
            accessor = accessor_dict[pin]            
            cell_status = self.status[accessor.cell][accessor.subpath]

            s = cell_status.data_status
            if s == Status.StatusDataEnum.INVALID:
                s = Status.StatusDataEnum.UPSTREAM_ERROR
            if s.value > new_status.data_status.value:
                new_status.data_status = s

            s = cell_status.auth_status
            if s.value > new_status.auth_status.value:
                new_status.auth_status = s
        
        if len(unconnected_list):
            new_status._unconnected_list = unconnected_list
        
        if new_status.data_status.value > Status.StatusDataEnum.PENDING.value:
            new_status.exec = "BLOCKED"
        elif new_status.data_status.value == Status.StatusDataEnum.PENDING.value:
            new_status.exec = "PENDING"
        
        backup_auth = None
        if full:
            if str(new_status.exec) in ("READY", "PENDING"):
                if old_status.exec == "FINISHED":
                    if new_status.auth == "FRESH":
                        backup_auth = new_status.auth  # to propagate downstream cells as obsolete;
                                                    # revert to backup_auth at the end of this function
                    new_status.auth = "OBSOLETE"
                elif old_status.exec == "BLOCKED":  
                    new_status.data = "PENDING"      
        self.status[transformer] = new_status
        propagate_data = (new_status.data != old_status.data)
        propagate_auth = (new_status.auth != old_status.auth)
        target_cells = tcache.transformer_to_cells[transformer]
        if new_status.exec == "FINISHED":
            self.unstable.discard(transformer)
        elif new_status.exec == "READY":
            assert new_status.data in ("OK", "PENDING")
            if len(target_cells) and \
              ( str(new_status.auth) in ("FRESH", "OVERRULED") \
                or backup_auth is not None
              ):
                self.unstable.add(transformer)
                self._schedule_transformer(transformer)
        elif new_status.exec == "BLOCKED":
            if transformer in self.unstable:
                self.unstable.remove(transformer)
            if old_status.exec != "BLOCKED":
                self._unschedule_transformer(transformer)
        propagations = []
        if propagate_data or propagate_auth or new_connection:
            data_status = new_status.data if propagate_data else None
            auth_status = new_status.auth if propagate_auth else None
            if new_connection and new_status.data == "OK":
                if str(new_status.exec) in ("PENDING", "READY", "EXECUTING"):
                    data_status = "PENDING"            
            for cell, subpath in target_cells:                
                propagations += self._propagate_status(cell, data_status, auth_status, 
                  full=False, cell_subpath=subpath
                )
            if backup_auth is not None:
                new_status.auth = backup_auth
            #print("UPDATE", transformer, old_status, "=>", new_status)
        self._resolve_propagations(propagations)

    def update_reactor_status(self, reactor, full):
        if reactor._destroyed: return ### TODO, shouldn't happen...
        rtreactor = self.reactors[reactor]
        old_status = self.status[reactor]
        new_status = Status("reactor")
        new_status.data, new_status.exec, new_status.auth = "OK", "FINISHED", "FRESH"
        updated_pins = []
        propagations = []
        for pinname, pin in reactor._pins.items():
            if pin.io in ("output", "edit"):
                continue
            accessor = rtreactor.input_dict[pinname]
            cell = accessor.cell
            subpath = accessor.subpath
            cell_status = self.status[cell][subpath]

            s = cell_status.data_status
            if s == Status.StatusDataEnum.INVALID:
                s = Status.StatusDataEnum.UPSTREAM_ERROR
            if s.value > new_status.data_status.value:
                new_status.data_status = s

            s = cell_status.auth_status
            if s.value > new_status.auth_status.value:
                new_status.auth_status = s
        
        if new_status.data_status.value > Status.StatusDataEnum.PENDING.value:
            new_status.exec = "BLOCKED"
        if new_status.data_status.value == Status.StatusDataEnum.PENDING.value:
            new_status.exec = "PENDING"
        elif new_status.data != "UNDEFINED":
            if full and len(rtreactor.updated) and rtreactor.live is not None:
                self.status[reactor] = new_status
                ok = rtreactor.execute()
                new_status = self.status[reactor]
                rtreactor.updated.clear()
        if old_status != new_status:
            #print("reactor update", reactor)
            #print("reactor status OLD", old_status, "(", old_status.data, old_status.exec, old_status.auth, ")")
            #print("reactor status NEW", new_status, "(", new_status.data, new_status.exec, new_status.auth, ")")            
            if not full:
                propagate_data = (new_status.data != old_status.data)
                propagate_auth = (new_status.auth != old_status.auth)
                data_status = new_status.data if propagate_data else None
                auth_status = new_status.auth if propagate_auth else None
                for pinname, pin in reactor._pins.items():
                    if pin.io != "output":
                        continue
                    for cell, subpath in rtreactor.output_dict[pinname]:
                        propagations += self._propagate_status(cell, data_status, auth_status, full=False, cell_subpath=subpath)
        self._resolve_propagations(propagations)

    def update_macro_status(self, macro):
        if macro._destroyed: return ### TODO, shouldn't happen...
        old_status = self.status[macro]
        new_status = Status("macro")
        new_status.data, new_status.exec, new_status.auth = "OK", "FINISHED", "FRESH"
        updated_pins = []
        for pinname, pin in macro._pins.items():
            accessor = macro.input_dict[pinname]
            cell = accessor.cell
            subpath = accessor.subpath
            cell_status = self.status[cell][subpath]

            s = cell_status.data_status
            if s == Status.StatusDataEnum.INVALID:
                s = Status.StatusDataEnum.UPSTREAM_ERROR
            if s.value > new_status.data_status.value:
                new_status.data_status = s

            s = cell_status.auth_status
            if s.value > new_status.auth_status.value:
                new_status.auth_status = s
        
        if new_status.data_status.value > Status.StatusDataEnum.PENDING.value:
            new_status.exec = "BLOCKED"
        if new_status.data_status.value == Status.StatusDataEnum.PENDING.value:
            new_status.exec = "PENDING"
        elif new_status.data != "UNDEFINED":
            self.status[macro] = new_status
            macro._execute()
            new_status = self.status[macro]
        if old_status != new_status:
            self.status[macro] = new_status

    def update_worker_status(self, worker, full):
        from . import Transformer, Reactor, Macro
        if isinstance(worker, Transformer):
            return self.update_transformer_status(worker, full=full)
        elif isinstance(worker, Reactor):
            rtreactor = self.reactors[worker]
            for pinname, pin in worker._pins.items():
                if pin.io == "input":
                    io_dict = rtreactor.input_dict
                elif pin.io == "output":
                    io_dict = rtreactor.output_dict
                elif pin.io == "edit":
                    io_dict = rtreactor.edit_dict
                if pinname not in io_dict:
                    break
            else:
                return self.update_reactor_status(worker, full=full)
        elif isinstance(worker, Macro):
            return self.update_macro_status(worker)
        else:
            raise TypeError(worker, type(worker))

    def update_accessor_accessor(self, source, target, only_if_defined=False):
        assert source.source_access_mode is None
        assert source.source_content_type is None
        assert target.source_access_mode is None
        assert target.source_content_type is None
        same = True
        hsource = hash(source)
        if hsource in self._processed_accessors:
            return
        self._processed_accessors[hsource] = source
        if source.cell._destroyed or target.cell._destroyed: return ### TODO, shouldn't happen...
        checksum = self.cell_cache.cell_to_buffer_checksums.get(source.cell) # TODO in case of cache tree depth
        if checksum is None and only_if_defined:
            return
        last_checksum = source.last_buffer_checksum
        if checksum is not None and checksum == last_checksum:
            return
        """            
        for attr in ("celltype", "storage_type", "access_mode", "content_type"):
            if getattr(source, attr) != getattr(target, attr):
                same = False
        """
        if source.subpath is not None or target.subpath is not None:
            same = False
        for attr in ("storage_type", "access_mode"):
            if getattr(source, attr) != getattr(target, attr):
                same = False
        if same:
            if source.celltype != target.celltype:                
                print("Manager.py, line 1271: kludge for cson-plain types")
                assert source.celltype == "cson" and target.celltype == "plain"
                expression = source.to_expression(checksum)
                value = self.get_expression(expression)
                result = deserialize(
                    target.celltype, target.cell._subcelltype, target.cell.path,
                    value, from_buffer=False, buffer_checksum=None,
                    source_access_mode="plain", #bad
                    source_content_type="cson" #bad
                )
                target_buffer, target_checksum, target_obj, target_semantic_obj, target_semantic_checksum = result
                assert target.subpath is None                
                self.set_cell(
                    target.cell, target_semantic_obj,
                    subpath = None,
                    from_buffer=False, 
                    origin=source.cell
                )
            else:                
                self.set_cell_checksum(target.cell, checksum, self.status[source.cell][None])
        elif source.subpath is not None or target.subpath is not None:
            if source.celltype != target.celltype and target.celltype == "mixed" and source.celltype in ("plain","text"): ## KLUDGE
                pass
            elif source.celltype != target.celltype and source.celltype == "mixed" and target.celltype == "text": ## KLUDGE
                pass
            elif source.celltype != target.celltype and source.celltype == "mixed" and target.celltype == "plain": ## KLUDGE
                pass
            elif source.celltype != target.celltype: 
                raise NotImplementedError(source.cell, target.cell) ### cache branch
            expression = source.to_expression(checksum)
            try:
                value = self.get_expression(expression)
            except CacheMissError:
                value = None
            if value is not None:
                from_mixed = False
                if source.celltype == "mixed":
                    from_mixed = True
                elif source.access_mode == "mixed":
                    from_mixed = True
                if not isinstance(value, tuple): from_mixed=False ###KLUDGE
                if from_mixed:
                    storage, form, value = value
            if target.subpath is None:
                self.set_cell(
                    target.cell, value,
                    subpath = None,
                    from_buffer=False, 
                    origin=source.cell
                )
            else:
                if target.cell._silk is not None:
                    ### TODO: can be cleaner?                  
                    silk = target.cell._silk
                    if len(target.subpath):
                        if silk.data.get_path().value is None:
                            if isinstance(target.subpath[0], int):
                                silk = silk.set([])
                            else:
                                silk = silk.set({})
                        for p in target.subpath[:-1]:
                            if p not in silk and not isinstance(p, int):
                                silk[p] = {}
                            silk = silk[p]
                        silk[target.subpath[-1]] = value
                    else:
                        silk.set(value)
                else:
                    assert hasattr(target.cell, "_monitor")
                    monitor = target.cell._monitor
                    assert monitor is not None
                    monitor.set_path(target.subpath, value)
        else:
            raise NotImplementedError ### cache branch

    def update_path_value(self, path):
        # Slow! needs to be improved (TODO)
        from .macro import Path
        assert path._cell is not None
        if path._cell._destroyed: return ### TODO, shouldn't happen...
        for source, target in self.cell_to_cell:
            if isinstance(source, tuple):
                spath, subpath = source
                assert isinstance(spath, Path)
                if spath != path:
                    continue
                source = self.get_default_accessor(path._cell)
                source.subpath = subpath
            if isinstance(target, tuple):
                tpath, subpath = target
                assert isinstance(tpath, Path)
                if tpath._cell is None:
                    continue
                if tpath._cell._destroyed: continue ### TODO, shouldn't happen...
                target = self.get_default_accessor(tpath._cell)                
                target.subpath = subpath
            self.update_accessor_accessor(source, target)

    def update_cell_to_cells(self, cell, data_status, auth_status, *, subpath, full, origin):
        # Slow! needs to be improved (TODO)
        propagations = []
        from .macro import Path  
        for source, target in self.cell_to_cell:
            if isinstance(source, tuple):
                path, s_subpath = source
                assert isinstance(path, Path)
                if path._cell is not cell:
                    continue
                if s_subpath != subpath:
                    continue
                source = self.get_default_accessor(path._cell)
                source.subpath = s_subpath              
            else: #accessor
                if source.cell is not cell:
                    continue
                if source.subpath != subpath:
                    continue
            if isinstance(target, tuple):
                path, t_subpath = target
                assert isinstance(path, Path)
                tcell = path._cell
                if tcell is None:
                    continue
                target_accessor = self.get_default_accessor(tcell)
                target_accessor.subpath = t_subpath
            else:
                target_accessor = target
                tcell = target.cell
            assert tcell is not cell, (source, target, source.cell, cell)
            if full:                             
                propagation = partial(self.update_accessor_accessor, source, target_accessor)
                propagations.append(propagation)
            else:
                propagations += self._propagate_status(
                  tcell, data_status, auth_status, 
                  full=False, cell_subpath=subpath
                )            
        self._resolve_propagations(propagations)

    def _update_status(self, cell, defined, *, 
      has_auth, origin, cell_subpath, delay=False
    ):
        if delay:
            work = partial(self._update_status,
                cell, defined, 
                has_auth=has_auth,
                origin=origin,
                cell_subpath=cell_subpath,
                delay=False
            )
            self.workqueue.append(work)
            return

        if cell._destroyed:
            return
        status = self.status[cell][cell_subpath]
        old_data_status = status.data
        old_auth_status = status.auth        
        if not defined:
            status.data = "UNDEFINED"
        else:
            status.data = "OK"
        if not has_auth:
            status.auth = "OVERRULED"
        new_data_status = status.data if status.data != old_data_status else None
        new_auth_status = status.auth if status.auth != old_auth_status else None
        propagations = self._propagate_status(
            cell, new_data_status, new_auth_status, 
            full=True, origin=origin, cell_subpath=cell_subpath
        )
        self._resolve_propagations(propagations)
        self.schedule_jobs()

"""