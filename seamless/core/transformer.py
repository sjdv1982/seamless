from collections import deque, OrderedDict
import traceback
import os
import time
from functools import partial

from .worker import Worker, InputPin, OutputPin
from .pythreadkernel import Transformer as KernelTransformer
import threading

class Transformer(Worker):
    """
    This is the main-thread part of the transformer
    """
    transformer = None
    transformer_thread = None
    output_thread = None
    active = False
    _destroyed = False

    def __init__(self, transformer_params):
        super().__init__()
        self.state = {}
        self.code = InputPin(self, "code", "ref", "pythoncode")
        thread_inputs = []
        self._io_attrs = ["code"]
        self._pins = {"code":self.code}
        self._output_name = None
        self._connected_output = False
        self._last_value = None
        self._last_value_preliminary = False
        self._message_id = 0
        self._transformer_params = OrderedDict()
        for p in sorted(transformer_params.keys()):
            param = transformer_params[p]
            self._transformer_params[p] = param
            pin = None
            io, mode, submode = None, "copy", None
            if isinstance(param, str):
                io = param
            elif isinstance(param, (list, tuple)):
                io = param[0]
                if len(param) > 1:
                    mode = param[1]
                if len(param) > 2:
                    submode = param[2]
            if io == "input":
                pin = InputPin(self, p, mode, submode)
                thread_inputs.append(p)
            elif io == "output":
                pin = OutputPin(self, p, mode, submode)
                assert self._output_name is None  # can have only one output
                self._output_name = p
            else:
                raise ValueError(io)

            if pin is not None:
                self._io_attrs.append(p)
                self._pins[p] = pin

        """Output listener thread
        - It must have the same memory space as the main thread
        - It must run async from the main thread
        => This will always be a thread, regardless of implementation
        """
        self.output_finish = threading.Event()
        self.output_queue = deque()
        self.output_semaphore = threading.Semaphore(0)

        """Transformer thread
        For now, it is implemented as a thread
         However, it could as well be implemented as process
        - It shares no memory space with the main thread
          (other than the deques and semaphores, which could as well be
           implemented using network sockets)
        - It must run async from the main thread
        TODO: in case of process, synchronize registrars (use execnet?)
        """

        self.transformer = KernelTransformer(
            self,
            thread_inputs, self._output_name,
            self.output_queue, self.output_semaphore
        )

    def __str__(self):
        ret = "Seamless transformer: " + self.format_path()
        return ret

    def activate(self):
        if self.active:
            return

        thread = threading.Thread(target=self.listen_output, daemon=True) #TODO: name
        self.output_thread = thread
        self.output_thread.start()

        thread = threading.Thread(target=self.transformer.run, daemon=True) #TODO: name
        self.transformer_thread = thread
        self.transformer_thread.start()

        self.active = True


    def receive_update(self, input_pin, value):
        self._message_id += 1
        self._pending_updates += 1
        msg = (self._message_id, input_pin, value)
        self.transformer.input_queue.append(msg)
        self.transformer.semaphore.release()

    def listen_output(self):
        # TODO logging
        # TODO requires_function cleanup

        # This code is very convoluted... networking expert wanted for cleanup!

        def get_item():
            self.output_semaphore.acquire()
            if self.output_finish.is_set():
                if not self.output_queue:
                    return
            output_name, output_value = self.output_queue.popleft()
            return output_name, output_value

        def receive_end():
            nonlocal updates_on_hold
            if updates_on_hold:
                for n in range(100): #100x5 ms
                    ok = self.output_semaphore.acquire(blocking=False)
                    if ok:
                        self.output_semaphore.release()
                        break
                    time.sleep(0.005)
                else:
                    self._pending_updates -= updates_on_hold
                    updates_on_hold = 0

        updates_on_hold = 0
        while True:
            try:
                if updates_on_hold:
                    """
                    Difficult situation. At the one hand, we can't hold on to
                    these processed updates forever:
                     It would keep the transformer marked as unstable, blocking
                      equilibrate().
                    On the other hand, an output_value could be just waiting
                    for us. If we decrement _pending_updates too early, this may
                    unblock equilibrate() while equilibrium has not been reached
                    The solution is that the kernel must respond within 500 ms
                    with an @START signal, and then a @END signal when the
                    computation is complete
                    """
                    for n in range(100): #100x5 ms
                        ok = self.output_semaphore.acquire(blocking=False)
                        if ok:
                            self.output_semaphore.release()
                            break
                        time.sleep(0.005)
                    else:
                        self._pending_updates -= updates_on_hold
                        updates_on_hold = 0

                item = get_item()
                if item is None:
                    break
                output_name, output_value = item
                if output_name == "@START":
                    between_start_end = True
                    item = get_item()
                    if item is None:
                        break
                    output_name, output_value = item
                    assert output_name in ("@PRELIMINARY", "@END"), output_name
                    if output_name == "@END":
                        between_start_end = False
                        receive_end()
                        item = get_item()
                        if item is None:
                            break
                        output_name, output_value = item

                if output_name is None and output_value is not None:
                    updates_processed = output_value[0]
                    if self._pending_updates < updates_processed:
                        #This will not set the worker as stable
                        self._pending_updates -= updates_processed
                    else:
                        # hold on to updates_processed for a while, we don't
                        #  want to set the worker as stable before we have
                        #  done a send_update
                        updates_on_hold += updates_processed
                    continue

                preliminary = False
                if output_name == "@PRELIMINARY":
                    preliminary = True
                    output_name, output_value = item[1]
                elif between_start_end:
                    assert output_name == "@END", output_name
                    between_start_end = False
                    receive_end()
                    continue
                    item = get_item()
                    if item is None:
                        break
                    output_name, output_value = item

                assert output_name == self._output_name, item
                if self._connected_output:
                    pin = self._pins[self._output_name]
                    #use .partial, we're not in the main thread!
                    f = partial(pin.send_update, output_value,
                        preliminary=preliminary)
                    raise NotImplementedError #refactor add_work
                    import seamless
                    seamless.add_work(f)
                else:
                    print("OK!!", output_value)
                    self._last_value = output_value
                    self._last_value_preliminary = preliminary

                if preliminary:
                    continue

                item = get_item()
                if item is None:
                    break
                output_name, output_value = item
                assert output_name is None
                updates_processed = output_value[0]
                self._pending_updates -= updates_processed

                if updates_on_hold:
                    self._pending_updates -= updates_on_hold
                    updates_on_hold = 0
            except Exception:
                traceback.print_exc() #TODO: store it?

    def _on_connect_output(self):
        last_value = self._last_value
        if last_value is not None:
            self._last_value = None
            preliminary = self._last_value_preliminary
            self._last_value_preliminary = False
            self._pins[self._output_name].send_update(last_value,
                preliminary=preliminary)
        self._connected_output = True


    def destroy(self):
        if self._destroyed:
            return

        # gracefully terminate the transformer thread
        if self.transformer_thread is not None:
            self.transformer.finish.set()
            self.transformer.semaphore.release() # to unblock the .finish event
            self.transformer.finished.wait()
            self.transformer_thread.join()
            del self.transformer_thread
            self.transformer_thread = None

        # gracefully terminate the output thread
        if self.output_thread is not None:
            self.output_finish.set()
            self.output_semaphore.release() # to unblock for the output_finish
            self.output_thread.join()
            del self.output_thread
            self.output_thread = None

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())


    def status(self):
        """The computation status of the transformer
        Returns a dictionary containing the status of all pins that are not OK.
        If all pins are OK, returns the status of the transformer itself: OK or pending
        """
        result = {}
        for pinname, pin in self._pins.items():
            s = pin.status()
            if s != self.StatusFlags.OK.name:
                result[pinname] = s
        t = self.transformer
        for pinname in t._pending_inputs:
            if pinname not in result:
                result[pinname] = self.StatusFlags.PENDING.name
        if len(result):
            return result
        if t._pending_updates:
            return self.StatusFlags.PENDING.name
        if self.error is not None:
            return self.StatusFlags.ERROR.name
        return self.StatusFlags.OK.name

def transformer(params):
    return Transformer(params)
