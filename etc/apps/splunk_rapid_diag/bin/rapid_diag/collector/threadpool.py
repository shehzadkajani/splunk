# python imports
from __future__ import absolute_import
import threading
import sys
from time import time
from splunklib.six.moves.queue import Queue, Empty
from rapid_diag.collector.worker import Worker

# local imports
import logger_manager as log
from rapid_diag.conf_util import RapidDiagConf

_LOGGER = log.setup_logging("threadpool")


class SubscribableQueue(Queue, object):
    def __init__(self, subscribers, maxsize=0):
        super(SubscribableQueue, self).__init__(maxsize)
        self.subscribers = subscribers
        self.pending_count = 0
        self.lock = threading.Lock()

    def _alter_pending_count(self, delta):
        count = None
        with self.lock:
            self.pending_count += delta
            count = self.pending_count
        self.subscribers.adjust_threadpool_size(count)

    def put(self, item, block=True, timeout=None):
        super(SubscribableQueue, self).put(item, block, timeout)
        self._alter_pending_count(1)

    def task_done(self):
        super(SubscribableQueue, self).task_done()
        self._alter_pending_count(-1)


class ThreadPool(object):
    THREADPOOL_SIZE_SOFT_LIMIT, THREADPOOL_SIZE_HARD_LIMIT = RapidDiagConf.get_threadpool_size_limits()

    """ Pool of threads consuming tasks from a queue """

    def __init__(self, soft_limit=THREADPOOL_SIZE_SOFT_LIMIT, hard_limit=THREADPOOL_SIZE_HARD_LIMIT):
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.workers = []
        self.tasks = SubscribableQueue(self)
        self.add_workers(self.soft_limit)

    def add_workers(self, num_threads):
        for _ in range(num_threads):
            try:
                self.workers.append(Worker(self.tasks))
            except Exception as e:
                _LOGGER.exception("Error while creating worker. " + str(e))

    def adjust_threadpool_size(self, pending_count):
        """ Adjust the ThreadPool size """
        _LOGGER.debug("Threadpool: {}".format(str([w.getName() for w in self.workers])))
        if pending_count > self.get_total_workers_count() and self.get_total_workers_count() < self.hard_limit:
            thread_to_spawn = min(pending_count - self.get_total_workers_count(), self.hard_limit - self.get_total_workers_count())
            self.add_workers(thread_to_spawn)

    def get_total_workers_count(self):
        """ Return total number of worker """
        return len(self.workers)

    def add_task(self, func, *args):
        """ Add a task to the queue """
        token = ThreadPool.Token(func, *args)
        self.tasks.put((token,))
        return token

    def abort(self):
        """
        Completely thread-unsafe! Cannot be called concurrently with other uses of this singleton.
        """
        try:
            while not self.tasks.empty():
                self.tasks.get_nowait()
        except Empty:
            pass
        for i, w in enumerate(self.workers):
            w.start_shutdown()
            w.join()
            self.workers[i] = Worker(self.tasks)

    def __del__(self):
        self.abort()

    class Token(object):
        PENDING = 0
        RUNNING = 1
        FINISHED = 2

        def __init__(self, func, *args):
            self.func = func
            self.args = args
            self.result = None
            self.status = ThreadPool.Token.PENDING
            self.lock = threading.Lock()
            self.condVar = threading.Condition(self.lock)

        def __call__(self):
            with self.lock:
                assert(self.status == ThreadPool.Token.PENDING)
                self.status = ThreadPool.Token.RUNNING
            result = self.func(*self.args)
            with self.lock:
                assert(self.status == ThreadPool.Token.RUNNING)
                self.status = ThreadPool.Token.FINISHED
                self.result = result
                self.condVar.notifyAll()

        def wait(self, timeout=None, status=None):
            """
            Wait until object's status is at least `status`, return
            current status (which may be prior to the requested if
            `timeout is not None`)
            """

            if not status:
                status = ThreadPool.Token.FINISHED

            # None will get stuck in a C call forever, blocking signal handling -- just use a silly timeout instead
            if timeout is None:
                try:
                    timeout = threading.TIMEOUT_MAX
                except:
                    timeout = sys.maxsize
            end = time() + timeout
            with self.lock:
                while self.status < status:
                    timeout = end - time()
                    if timeout <= 0:
                        return self.status
                    self.condVar.wait(timeout)
                return self.status == ThreadPool.Token.FINISHED

        def get_result(self):
            assert(self.status == ThreadPool.Token.FINISHED)
            return self.result
