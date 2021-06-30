# python imports
import os
import sys
import json
import datetime

# Reloading the rapid_diag bin path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication

# local imports
import logger_manager as log
from rapid_diag_handler_utils import persistent_handler_wrap_handle
from rapid_diag.task_handler import TaskHandler

_LOGGER = log.setup_logging("static_task_information")


class StaticTaskInformationEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        handler = TaskHandler()
        tasks = handler.static_tasks_list()
        return {'payload': json.dumps(tasks), 'status': 200}

