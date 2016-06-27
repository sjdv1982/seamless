from . import Controller
from ..cell.manager import InputPin, OutputPin
from ..process.transformer import Transformer

from collections import deque
import threading
import traceback


class ExampleTransformer(Controller):
    """
    This is the main-thread part of the controller_ref
    """
    _requires_function = True
    thread = None

    def __init__(self, input_type, output_type):
        self.state = {}
        self.input = InputPin(self, "input")
        self.code = InputPin(self, "code")
        self.output = OutputPin()

        thread_inputs = {
          "input": input_type,
        }
        self._io_attrs = ("input", "code", "output")
        """Output listener thread
        - It must have the same memory space as the main thread
        - It must run async from the main thread
        => This will always be a thread, regardless of implementation
        """
        self.output_finish = threading.Event()
        self.output_queue = deque()
        self.output_semaphore = threading.Semaphore(0)
        thread = threading.Thread(target=self.listen_output, daemon=True)
        self.output_thread = thread
        self.output_thread.start()

        """Transformer thread
        For now, it is implemented as a thread
         However, it could as well be implemented as process
        - It shares no_func_required memory space with the main thread
          (other than the deques and semaphores, which could as well be
           implemented using network sockets)
        - It must run async from the main thread
        """
        self.transformer = Transformer(
         thread_inputs,
         self.output_queue,
         self.output_semaphore
        )
        thread = threading.Thread(target=self.transformer.run, daemon=True)
        self.transformer_thread = thread
        self.transformer_thread.start()

    def receive_update(self, input_pin, value):
        self.transformer.queue.append((input_pin, value))
        self.transformer.semaphore.release()

    def listen_output(self):
        while True:
            try:
                self.output_semaphore.acquire()
                if self.output_finish.is_set():
                    if not self.output_queue:
                        break

                output_value = self.output_queue.popleft()
                self.output.update(output_value)

            except:
                traceback.print_exc() #TODO: store it?

    def destroy(self):
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

        # free all input and output pins
        for attr in self._io_attrs:
            value = getattr(self, attr)
            if value is None:
                continue

            setattr(self, attr, None)
            del value

    def __del__(self):
        try:
            self.destroy()

        except Exception as err:
            print(err)
            pass
