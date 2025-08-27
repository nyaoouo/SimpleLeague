import contextlib
import inspect
import logging
import threading

logger = logging.getLogger(__name__)


class HandleManager:
    def __init__(self, lock=None):
        self.counter = 0
        self.free_handles = []
        self.lock = lock or contextlib.nullcontext()

    def is_valid(self, handle):
        return 0 < handle <= self.counter and handle not in self.free_handles

    def get_handle(self):
        with self.lock:
            if self.free_handles:
                return self.free_handles.pop()
            self.counter += 1
            return self.counter

    def free_handle(self, handle):
        with self.lock:
            if self.is_valid(handle):
                self.free_handles.append(handle)


def count_positional_args(func):
    count = 0
    for param in inspect.signature(func).parameters.values():
        if param.kind is param.VAR_POSITIONAL:
            return count, True
        elif param.kind is param.POSITIONAL_OR_KEYWORD:
            count += 1
        else:  # param.kind is param.KEYWORD_ONLY/ param.VAR_KEYWORD
            break
    return count, False


def call_with_args(func, args, default_fill=None):
    if not hasattr(func, 'callargs_'):
        # func.__callargs__ = count_positional_args(func)
        setattr(func, 'callargs_', count_positional_args(func))
    min_arg, has_varargs = getattr(func, 'callargs_')
    if len(args) < min_arg:
        args += (default_fill,) * (min_arg - len(args))
    elif len(args) > min_arg and not has_varargs:
        args = args[:min_arg]
    return func(*args)


class Listener:
    def __init__(self):
        self.listeners = {}
        self.handle2key = {}
        self.handle_manager = HandleManager()

    def set(self, event, func=None, *_, async_=False):
        if func is None:
            return lambda f: self.set(event, f, async_=async_)
        if event not in self.listeners:
            self.listeners[event] = []
        handle = self.handle_manager.get_handle()
        self.handle2key[handle] = event
        self.listeners[event].append((handle, (func, async_)))
        return handle

    def remove(self, handle):
        if handle in self.handle2key:
            event = self.handle2key.pop(handle)
            if event in self.listeners:
                self.listeners[event] = [(h, l) for h, l in self.listeners[event] if h != handle]
                if not self.listeners[event]: del self.listeners[event]
                self.handle_manager.free_handle(handle)

    def _call(self, evnet, func, args):
        try:
            func(*args)
        except Exception as e:
            logger.error(f"Error in listener for event '{evnet}' with func {func}: {e}", exc_info=True)

    def invoke(self, event, *args):
        for handle, (func, async_) in self.listeners.get(event, ()):
            if async_:
                threading.Thread(target=self._call, args=(event, func, args), daemon=True).start()
            else:
                self._call(event, func, args)
