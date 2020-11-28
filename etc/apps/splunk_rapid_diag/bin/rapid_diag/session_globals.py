from __future__ import absolute_import
import threading
from rapid_diag.collector.tool_manager import ToolAvailabilityManager
from rapid_diag.collector.threadpool import ThreadPool
from rapid_diag.process_abstraction import ProcessLister


class SessionGlobals(object):
    __objects = {}
    __lock = threading.Lock()

    @staticmethod
    def reset():
        with SessionGlobals.__lock:
            SessionGlobals.__objects = {}

    @staticmethod
    def get_tool_availability_manager():
        key = ToolAvailabilityManager.__name__
        with SessionGlobals.__lock:
            if key not in SessionGlobals.__objects:
                SessionGlobals.__objects[key] = ToolAvailabilityManager()
            return SessionGlobals.__objects[key]

    @staticmethod
    def get_threadpool():
        key = ThreadPool.__name__
        with SessionGlobals.__lock:
            if key not in SessionGlobals.__objects:
                SessionGlobals.__objects[key] = ThreadPool()
            return SessionGlobals.__objects[key]

    @staticmethod
    def get_process_lister():
        key = ProcessLister.__name__
        with SessionGlobals.__lock:
            if key not in SessionGlobals.__objects:
                SessionGlobals.__objects[key] = ProcessLister()
            return SessionGlobals.__objects[key]
