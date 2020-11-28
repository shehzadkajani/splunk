# python imports
from __future__ import absolute_import
import sys
import copy
from splunklib import six
from time import time
from threading import Lock, Condition
from abc import ABCMeta, abstractmethod

# local imports
import logger_manager as log
from rapid_diag.collector.collector_result import CollectorResult

_LOGGER = log.setup_logging("collector")


class CollectorStateObserver(six.with_metaclass(ABCMeta, object)):

    @abstractmethod
    def save(self):
        pass


class Collector(six.with_metaclass(ABCMeta, object)):
    MAX_TIME = float(30 * 24 * 60 * 60)
    MAX_CNT = int(1e9)

    class State:
        WAITING = 0
        STARTED = 1
        COLLECTING = 2
        ABORTING = 3
        FINISHED = 4
        SUCCESS = 5
        FAILURE = 6
        ABORTED = 7
        STATUS_STRINGS = {
            'Waiting': WAITING,
            'Started': STARTED,
            'Collecting': COLLECTING,
            'Aborting': ABORTING,
            'Finished': FINISHED,
            'Success': SUCCESS,
            'Failure': FAILURE,
            'Aborted': ABORTED
        }

        @staticmethod
        def valid(state):
            """validates the state value.

            Parameters
            ----------
            state : int
                state value

            Returns
            -------
            bool
                True if value is available in dict else False 
            """
            return state in Collector.State.STATUS_STRINGS.values()

        @staticmethod
        def get_status_code(state):
            """parses string value returns the state in int
            If value is not valid then return the default value 0. 

            Parameters
            ----------
            state : string
                human readable state value

            Returns
            -------
            int
                state value
            """
            if state not in Collector.State.STATUS_STRINGS.keys():
                _LOGGER.warning("Invalid state. Reseting to Initial State")
                return Collector.State.WAITING
            return Collector.State.STATUS_STRINGS[state]

        @staticmethod
        def get_status_string(state):
            """parses the int value returns the state in string 

            Parameters
            ----------
            state : int
                state value

            Returns
            -------
            string
                human readable state value
            """
            state_list = [key for key, value in Collector.State.STATUS_STRINGS.items() if value == state]
            if len(state_list) != 1:
                _LOGGER.warning("Invalid state=" + str(state) + ". Returning initial state.")
                return Collector.State.get_status_string(Collector.State.WAITING)
            return state_list[0]

    class RunContext:
        def __init__(self, outputDir, suffix, sessionToken, stateChangeObservers=None):
            self.outputDir = outputDir
            self.suffix = suffix
            self.sessionToken = sessionToken
            self.stateChangeObservers = stateChangeObservers if stateChangeObservers is not None else []

        def clone(self):
            return Collector.RunContext(copy.deepcopy(self.outputDir), copy.deepcopy(self.suffix),
                                        copy.deepcopy(self.sessionToken), self.stateChangeObservers[:])

    def __init__(self):
        self.state = Collector.State.WAITING
        self.state_lock = Lock()
        self.state_condvar = Condition(self.state_lock)
        self.observers = set()

    def promote_state(self, state, stateChangeObservers=None):
        assert Collector.State.valid(state)
        with self.state_lock:
            prev_state = self.state
            if state > self.state:
                self.state = state
                self.state_condvar.notifyAll()
                self.notifyObserver()
        if prev_state < state and stateChangeObservers is not None:
            for observer in stateChangeObservers:
                observer(self, prev_state, state)

    def wait_for_state(self, state, timeout=None):
        """
        Wait until object's state is at least `state`, return
        current state (which may be prior to the requested if
        `timeout is not None`)
        """
        assert Collector.State.valid(state)
        # None will get stuck in a C call forever, blocking signal handling -- just use a silly timeout instead
        if timeout is None:
            timeout = sys.maxsize
        end = time() + timeout
        with self.state_lock:
            while self.state < state:
                timeout = end - time()
                if timeout <= 0:
                    return self.state
                self.state_condvar.wait(timeout)
            return self.state

    def init_state(self):
        """
        resets the state to `WAITING(0)`
        NOTE: used for task re-run. Otherwise collectors will read final state values.
        """
        with self.state_lock:
            self.state = Collector.State.WAITING

    def get_state(self):
        """provides the current state of collector

        Returns
        -------
        int
            state value
        """
        with self.state_lock:
            return self.state

    def collect(self, runContext):
        """
        Execute collection tasks outputting files to `runContext.outputDir/<somename>runContext.suffix<.extension>`.
        """
        self.promote_state(Collector.State.STARTED, runContext.stateChangeObservers)
        try:
            result = self._collect_impl(runContext)
            return result
        except Exception as e:
            result = CollectorResult.Exception(e, "Error while collecting data from " +
                                             self.__class__.__name__, _LOGGER)
            return result
        finally:
            state = Collector.State.FINISHED
            if result.isSuccess():
                state = Collector.State.SUCCESS
            elif self.get_state() == Collector.State.ABORTING:
                state = Collector.State.ABORTED
            else:
                state = Collector.State.FAILURE
            self.promote_state(state, runContext.stateChangeObservers)

    @abstractmethod
    def _collect_impl(self, runContext):
        """
        `collect()` implementation method. This is protected and only meant for subclasses to extend -- hands off, users!
        """
        pass

    @abstractmethod
    def getType(self):
        """
        Return collector type (see `rapid_diag.collector.type`).
        """
        pass

    @abstractmethod
    def get_required_resources(self):
        """
        Return required resource list (see `rapid_diag.collector.resource`).
        """
        pass

    def registerObserver(self, observer):
        self.observers.add(observer)

    def removeObjserver(self, observer):
        self.observers.remove(observer)

    def notifyObserver(self):
        for observer in self.observers:
            with observer:
                observer.save()

    def apply_to_self(self, functor, depth=0):
        functor(self, depth)

    def cleanup(self, **kwargs):
        """
        Do cleanup after e.g. Abort.
        NOTE: Currently used in Windows specific scenario only
        """
        pass


if __name__ == '__main__':
    class Foo(Collector):
        def __init__(self, val):
            self.val = val
        def collect(self, runContext):
            pass
        def getType(self):
            pass
        def get_required_resources(self):
            pass
        def toJsonObj(self):
            pass
        @staticmethod
        def fromJsonObj(self):
            pass
    x = Foo(1)
    y = Foo(2)
    z = Foo(1)
    assert(x==z)
    assert(not x!=z)
    assert(y!=x)
    assert(not y==x)
    assert(z!=y)
    assert(not z==y)
