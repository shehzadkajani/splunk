from threading import Thread
from splunklib.six.moves.queue import Empty
# local imports
import logger_manager as log

# global variables
_LOGGER = log.setup_logging("worker")


class Worker(Thread):
    DATA_WAIT_TIMEOUT = 0.5

    """ Thread executing tasks from a given tasks queue """

    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.shutdown = False
        self.start()
        _LOGGER.debug(self.getName() + ' created in pool')

    def start_shutdown(self):
        self.shutdown = True

    def run(self):
        while not self.shutdown:
            try:
                task = self.tasks.get(True, self.__class__.DATA_WAIT_TIMEOUT)
            except Empty:
                continue

            token = task[0]
            args = []
            if len(task) > 1:
                args = task[1:]
            _LOGGER.debug('Passed values for func: ' + str(token.func) + ' args: ' + str(args))
            try:
                # token is calleble and it's calling func internally
                token(*args)
            except:
                # An exception happened in this thread
                _LOGGER.exception('An error occured. ')
            finally:
                _LOGGER.debug("Task Done: {}".format(token.func))
                # Mark this task as done, whether an exception happened or not
                self.tasks.task_done()
