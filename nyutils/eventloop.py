import dataclasses
import logging
import threading
import time
import typing
import bisect

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class Event:
    loop: 'EventLoop'
    func: typing.Callable
    args: typing.Tuple
    kwargs: typing.Dict
    delay: float
    repeat: bool
    next_time: float
    thread: bool


class EventLoop:

    def __init__(self):
        self._events_by_time = []
        self._events_by_id = {}
        self.lock = threading.Lock()
        self._update = threading.Event()
        self._serve_thread = threading.Thread(target=self.serve, daemon=True)
        self._terminate = False

    def create_event(self, func: typing.Callable, args=None, kwargs=None, delay: float = 0, repeat: bool = False, timestamp=None, thread=False):
        if delay == 0 and repeat:
            raise ValueError("Cannot repeat an event with zero delay")
        args = args or ()
        kwargs = kwargs or {}
        next_at = timestamp or time.time() + delay
        evt = Event(self, func, args, kwargs, delay, repeat, next_at, thread)
        handle = id(evt)
        with self.lock:
            idx = bisect.bisect_left(self._events_by_time, evt.next_time, key=lambda e: e.next_time)
            self._events_by_time.insert(idx, evt)
            # bisect.insort(self._events_by_time, evt, key=lambda e: e.next_time)
            self._events_by_id[handle] = evt

        if logger.isEnabledFor(logging.DEBUG):
            fmt_next_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(evt.next_time))
            logger.debug(f'Event {func} scheduled at {fmt_next_at} ({evt.next_time - time.time():.2f}s from now)')
        if idx == 0:
            self.trigger_update()
        return handle

    def cancel_event(self, handle):
        with self.lock:
            if (evt := self._events_by_id.pop(handle, None)) is None:
                return False
            et = self._events_by_time
            idx_ = bisect.bisect_left(et, evt.next_time, key=lambda e: e.next_time)
            while idx_ < len(et) and et[idx_].next_time == evt.next_time:
                if et[idx_] is evt:
                    et.pop(idx_)
                    break
                idx_ += 1
            if idx_ == 0:
                self.trigger_update()
        return True

    def clear(self):
        with self.lock:
            self._events_by_time.clear()
            self._events_by_id.clear()
        self.trigger_update()

    def trigger_update(self):
        if not (self._serve_thread and self._serve_thread.is_alive()):
            if not self._events_by_id: return
            self._serve_thread = threading.Thread(target=self.serve, daemon=True)
            self._serve_thread.start()
        self._update.set()

    def update(self):
        self._update.clear()
        if self._terminate:
            return 0
        now = time.time()
        et = self._events_by_time
        while et and et[0].next_time <= now:
            evt = et.pop(0)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f'Event {evt.func} executed')
            if evt.thread:
                threading.Thread(target=evt.func, args=evt.args, kwargs=evt.kwargs, daemon=True).start()
            else:
                try:
                    evt.func(*evt.args, **evt.kwargs)
                except Exception as e:
                    logger.error(f'Error in event {evt.func}', exc_info=e)
            if evt.repeat:
                evt.next_time += evt.delay
                bisect.insort(et, evt, key=lambda e: e.next_time)
                if logger.isEnabledFor(logging.DEBUG):
                    fmt_next_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(evt.next_time))
                    logger.debug(f'Repeated event {evt.func} scheduled at {fmt_next_at} ({evt.next_time - time.time():.2f}s from now)')
            else:
                self._events_by_id.pop(id(evt), None)

        if not self._events_by_time:
            return None
        return self._events_by_time[0].next_time - time.time()

    def serve(self):
        while not self._terminate:
            self._update.wait(self.update())

    def terminate(self):
        self._terminate = True
        self.trigger_update()
        return self._serve_thread.join


def test():
    loop = EventLoop()
    new = time.time()

    def print_hello():
        print(f"{time.time() - new:.2f} Hello")

    handle = loop.create_event(print_hello, (), {}, delay=1, repeat=True)
    time.sleep(2.5)
    handle2 = loop.create_event(print_hello, (), {}, delay=1.1, repeat=True)
    time.sleep(3.4)
    print(loop.cancel_event(handle))
    time.sleep(2)
    print(loop.cancel_event(handle2))
    time.sleep(2)


if __name__ == '__main__':
    test()
