'''
.unstable

        self.jobs = {}  # jobid-to-job
        self.executing = {}  # level2-transformer-to-jobid
        self.scheduled = []  # list of type-schedop-(add/remove) tuples
                             # type = "transformer", schedop = level1 transformer
                             # type = "macro", schedop = Macro object
                             # type = "reactor", schedop = (Reactor object, pin name, expression)
        self._temp_tf_level1 = {} ### DO WE NEED THIS??


    async def _schedule_transformation_all(self, tf_level1, count, from_remote=False, debug=False):
        """Runs until either a remote cache hit has been obtained, or a job has been submitted"""
        from .cache.transform_cache import TransformerLevel1
        assert isinstance(tf_level1, TransformerLevel1)
        tcache = self.transform_cache
        htf_level1 = tf_level1.get_hash()
        result = tcache.get_result(htf_level1)
        if result is not None:
            self.set_transformation_result(tf_level1, None, None, result, False)
            return
        task = None
        try:
            if not from_remote:
                task = self.cache_task_manager.remote_transform_result(htf_level1)
                if task is not None:
                    await task.future
                    result = task.future.result()
                    if result is not None:
                        self.set_transformation_result(tf_level1, None, None, result, False)
                        return
                try:
                    tf_level2 = await tcache.build_level2(tf_level1)
                except (ValueError, CacheMissError):
                    pass
                except:
                    import traceback
                    traceback.print_exc()
                else:                    
                    if tf_level2 is None:
                        print("Cannot build transformation level 2")
                        self.set_transformation_undefined(tf_level1)
                        return
                    htf_level2 = tf_level2.get_hash()
                    result = tcache.get_result_level2(htf_level2)
                    if result is not None:
                        self.set_transformation_result(tf_level1, tf_level2, None, result, False)
                        return
                    task = self.cache_task_manager.remote_transform_result_level2(tf_level2.get_hash())
                    if task is not None:
                        await task.future
                        result = task.future.result()
                        if result is not None:
                            self.set_transformation_result(tf_level1, tf_level2, None, result, False)
                            return
                task = None
                job = self.jobscheduler.schedule_remote(tf_level1, count)
                if job is not None:
                    return
                if tcache.transformer_from_hlevel1.get(htf_level1) is None: # job must have been cancelled
                    return
            return await self._schedule_transformation_job(tf_level1, count, 
              from_remote=from_remote, debug=debug
            )
        except asyncio.CancelledError:
            if task is not None:
                task.cancel()
        except:
            print("ERR!")
            raise

    async def _schedule_transformation_job(self, 
      tf_level1, count, *,
      from_remote=False, from_stream=False, debug=False
    ):
        from .cache.transform_cache import TransformerLevel1
        if from_stream or from_remote:
            assert debug == False
        assert isinstance(tf_level1, TransformerLevel1)        
        if tf_level1._stream_params is not None:
            return await self._schedule_transformation_stream_job(tf_level1, count, from_remote=from_remote)
        tcache = self.transform_cache
        try:
            tf_level2 = await tcache.build_level2(tf_level1)
        except CacheMissError as exc:
            print("ERROR: build level 2, CacheMissError:", exc)
            raise
        tcache.set_level2(tf_level1, tf_level2)
        result = tcache.result_hlevel2.get(tf_level2.get_hash())
        if result is not None:            
            self.set_transformation_result(tf_level1, tf_level2, None, result, False)
            return
        transformer_can_be_none = from_remote or from_stream
        job = self.jobscheduler.schedule(tf_level2, count, transformer_can_be_none, debug=debug)
        return job

    async def _schedule_transformation_stream_job(self, tf_level1, count, from_remote=False):
        from .cache.transform_cache import TransformerLevel1
        tcache = self.transform_cache
        stream_params = tf_level1._stream_params
        if len(stream_params) > 1: raise NotImplementedError
        for k,v in stream_params.items():
            if v != "map": raise NotImplementedError
        k = list(stream_params.keys())[0]
        expressions = copy.deepcopy(tf_level1._expressions)
        e = expressions[k]
        value = self.get_expression(e)
        if isinstance(value, (list, np.ndarray)):
            items = range(len(value))
        elif isinstance(value, dict):
            items = value.keys()
        old_subpath = () if e.subpath is None else e.subpath
        items_level1 = {}
        stream_status = self.stream_status
        transformers = []
        hlevel1 = tf_level1.get_hash()
        for ttf, ttf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if ttf_level1.get_hash() != hlevel1:
                continue
            transformers.append(ttf)
        job_coros = []
        for item in items:
            e.subpath = old_subpath + (item,)
            item_level1 = TransformerLevel1(expressions, None, tf_level1.output_name)
            tcache.incref(item_level1)
            items_level1[item] = item_level1            
        for tf in transformers:
            tcache.stream_transformer_to_levels1[tf] = copy.copy(items_level1)
        
        for item in items:
            item_level1 = items_level1[item]
            for tf in transformers:
                stream_status[tf, item] = copy.deepcopy(self.status[tf])
            job_coro = self._schedule_transformation_job(
                item_level1, count, from_remote=from_remote, from_stream=True
            )
            job_coros.append(job_coro)
        jobs = []
        if len(job_coros):
            jobs0 = await asyncio.gather(*job_coros)
            for job in jobs0:
                if job is not None:   
                    jobs.append(job)
        return self.jobscheduler.jobarray(jobs)

    async def run_remote_transform_job(self, tf_level1):
        tcache = self.transform_cache
        vcache = self.value_cache
        tcache.incref(tf_level1)
        hlevel1 = tf_level1.get_hash()         
        if hlevel1 not in tcache.transformer_from_hlevel1:
            tcache.transformer_from_hlevel1[hlevel1] = None
        try:
            coros = []
            for k in tf_level1._expressions:
                checksum = tf_level1._expressions[k].buffer_checksum
                coro = self.get_value_from_checksum_async(checksum)
                coros.append(coro)
            await asyncio.gather(*coros)
            for k in tf_level1._expressions:
                checksum = tf_level1._expressions[k].buffer_checksum
                assert vcache.get_buffer(checksum) is not None, (k, checksum.hex())
            job = await self._schedule_transformation_all(tf_level1, 1, from_remote=True)
            if job is not None and job.future is not None:
                await job.future                        
            result = tcache.get_result(hlevel1)
            return result
        finally:            
            #tcache.decref(tf_level1) #TODO: transformers that expire...
            real_transformer = tcache.transformer_from_hlevel1.pop(hlevel1, None)
            if real_transformer is not None:
                tcache.transformer_from_hlevel1[hlevel1] = real_transformer

    def schedule_jobs(self):
        from ..communionserver import communionserver
        communionserver.wait(self)
        if not len(self.scheduled):
            return
        tcache = self.transform_cache
        scheduled_clean = OrderedDict()
        for type, schedop, add_remove, debug in self.scheduled:            
            key = type, schedop.get_hash()
            if key not in scheduled_clean:
                count = 0
            else:
                old_schedop, count, _ = scheduled_clean[key]
                assert old_schedop.get_hash() == schedop.get_hash()
            dif = 1 if add_remove else -1
            scheduled_clean[key] = schedop, count + dif, debug
        for key, value in scheduled_clean.items():
            type, _ = key
            schedop, count, debug = value
            if count == 0:
                continue
            if type == "transformer":
                tf_level1 = schedop
                hlevel1 = tf_level1.get_hash()
                if count > 0:                    
                    for ttf, ttf_level1 in tcache.transformer_to_level1.items():
                        if ttf_level1.get_hash() != hlevel1:
                            continue
                        status = self.status[ttf]
                        if status.exec == "READY":
                            status.exec = "EXECUTING" 
                    for ttf, ttf_levels1 in tcache.stream_transformer_to_levels1.items():
                        for k, ttf_level1 in ttf_levels1.items():
                            if ttf_level1.get_hash() != hlevel1:
                                continue
                            status = self.stream_status[ttf, k]
                            if status.exec == "READY":
                                status.exec = "EXECUTING"

                    task = self._schedule_transformation_all(tf_level1, count, debug=debug)
                    self.cache_task_manager.schedule_task(
                        ("transform","all",tf_level1),task,count,
                        cancelfunc=None, resultfunc=None
                    )
                else:
                    task = self._schedule_transformation_job(tf_level1, count, debug=debug)
                    self.cache_task_manager.schedule_task(
                        ("transform","job",tf_level1),task,count,
                        cancelfunc=None, resultfunc=None)
            else:
                raise ValueError(type)
        self.scheduled = []
        self._temp_tf_level1.clear()


    def set_transformation_result_exception(self, level1, level2, exception):
        #TODO: store exception
        transformer = None
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        hlevel2 = None
        if level2 is not None:
            hlevel2 = level2.get_hash()
        transformers = []
        propagations = []
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            htflevel1 = tf_level1.get_hash()
            if htflevel1 != hlevel1:
                if hlevel2 is None:
                    continue
                if htflevel1 not in tcache.hlevel1_to_level2:
                    continue
                if tcache.hlevel1_to_level2[htflevel1].get_hash() != hlevel2:
                    continue
            if transformer is None:
                transformer = tf, None
            transformers.append((tf, None))
        for tf, tf_levels1 in list(tcache.stream_transformer_to_levels1.items()): #could be more efficient...            
            for k, tf_level1 in tf_levels1.items():                
                htflevel1 = tf_level1.get_hash()
                if htflevel1 != hlevel1:
                    if hlevel2 is None:
                        continue
                    if htflevel1 not in tcache.hlevel1_to_level2:
                        continue
                    if tcache.hlevel1_to_level2[htflevel1].get_hash() != hlevel2:
                        continue
                if transformer is None:
                    transformer = tf, k
                transformers.append((tf, k))
        for tf, k in transformers:
            if k is None:
                tstatus = self.status[tf]
            else:
                tstatus = self.stream_status[tf, k]
            tstatus.exec = "ERROR"
            tstatus.data = "UNDEFINED"
            auth_status = None
            if tstatus.auth != "FRESH":
                auth_status = "FRESH"
                tstatus.auth = "FRESH"
            self.unstable.discard(tf)
            for cell, subpath in tcache.transformer_to_cells[tf]:
                propagations += self._propagate_status(
                  cell,"UPSTREAM_ERROR", auth_status, 
                  cell_subpath=subpath, full=False
                )
        
        if transformer is None:
            transformer = "<Unknown transformer>", None
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        kstr = "" if transformer is None else ", stream element %s" % transformer[1]
        msg = "Exception in %s%s:\n" % (transformer[0], kstr) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)
        self._resolve_propagations(propagations)


    def set_transformation_undefined(self, level1):
        if self._destroyed:
            return
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if tf_level1.get_hash() != hlevel1:
                continue
            tstatus = self.status[tf]
            tstatus.exec = "BLOCKED"
            tstatus.data = "UNDEFINED"
            tstatus.auth = "OBSOLETE" # To provoke an update            
            self.update_transformer_status(tf,full=False)
            self.unstable.discard(tf)

    def set_transformation_result(self, level1, level2, value, checksum, prelim):
        from .link import Link
        from .macro import Path

        if prelim: raise NotImplementedError # livegraph branch

        # TODO: would be better if there was only checksum, generated with protocol.calc_buffer
        #  This corresponds to the behavior of a cache hit from transform result
        # TODO: this function is not checked for exceptions when called from a remote job...""
        if self._destroyed:
            return
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        is_none = (value is None and checksum is None)
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if tf_level1.get_hash() != hlevel1:
                continue
            tstatus = self.status[tf]
            tstatus.exec = "FINISHED"
            tstatus.data = "OK"
            tstatus.auth = "OBSOLETE" # To provoke an update            
            for cell, subpath in tcache.transformer_to_cells[tf]:
                if isinstance(cell, Link):
                    cell = cell.linked()
                if isinstance(cell, Path):
                    cell = cell._cell
                    if cell is None:
                        continue
                if not hasattr(cell, "_monitor") or cell._monitor is None:                    
                    if subpath == ():
                        subpath = None            
                    if subpath is not None:
                        raise Exception(subpath)
                status = self.status[cell][subpath]
                if prelim:
                    if status.auth == "FRESH":
                        status.auth = "PRELIMINARY"
                else:
                    if status.auth == "PRELIMINARY":
                        status.auth = "FRESH"
                if value is None and not is_none:
                    accessor = self.get_default_accessor(cell)
                    accessor.celltype = "mixed" #generated with protocol.calc_buffer
                    accessor.subpath = subpath
                    expression = accessor.to_expression(checksum)
                    value = self.get_expression(expression)
                    if value is not None:
                        try:
                            _, _, value = value
                        except (TypeError, ValueError): #KLUDGE
                            pass
                if value is not None or subpath is not None:
                    if subpath is None:                        
                        self.set_cell(cell, value, subpath=None)                        
                    else:              
                        assert hasattr(cell, "_monitor")
                        monitor = cell._monitor
                        assert monitor is not None
                        monitor.set_path(subpath, value)
                    if checksum is None and value is not None and subpath is not None:
                        checksum = self.cell_cache.cell_to_buffer_checksums[cell]
                else:                    
                    if cell._destroyed:
                        raise Exception(cell.name)
                    self.set_cell(None)
            self.update_transformer_status(tf,full=False)
        if checksum is None: #result conforms to no cell (remote transformation, stream transformation, or subpath)
            checksum, buffer = protocol.calc_buffer(value)
            self.value_cache.incref(checksum, buffer, has_auth=False)
        tcache.set_result(hlevel1, checksum)
        if level2 is not None:
            tcache.set_result_level2(level2.get_hash(), checksum)
        if not prelim:
            for tf, tf_levels1 in list(tcache.stream_transformer_to_levels1.items()): #could be more efficient...
                for k, tf_level1 in tf_levels1.items():
                    if tf_level1.get_hash() != hlevel1:
                        continue
                    self.set_transformation_stream_result(tf, k)        
        self.schedule_jobs()

    def set_transformation_stream_result(self, tf, k):
        """Set one element k of a stream transformer result"""
        tcache = self.transform_cache
        vcache = self.value_cache
        tstatus = self.stream_status[tf, k]
        tstatus.exec = "FINISHED"
        tstatus.data = "OK"
        tf_levels1 = tcache.stream_transformer_to_levels1[tf]        
        for k2, tf_level1 in tf_levels1.items():
            tstatus2 = self.stream_status[tf, k2]
            if tstatus2 != "FINISHED":
                break
        else:
            result = {}
            for k2, tf_level1 in tf_levels1.items():
                k2_checksum = tcache.get_result(tf_level1.get_hash())
                k2_buffer = self.value_cache.get_buffer(k2_checksum)[2]
                k2_result = deserialize(
                    "mixed", None,  (),
                    k2_buffer, from_buffer=True, buffer_checksum=k2_checksum,
                    source_access_mode=None, 
                    source_content_type=None
                )
                k2_value = k2_result[2][2]
                result[k2] = k2_value
            if isinstance(k, int):
                result = [result[n] for n in range(len(result))]
            level1 = tcache.transformer_to_level1[tf]
            self.set_transformation_result(level1, None, result, None, False)

        #raise NotImplementedError

'''