# python imports
import os
import sys
import json
import datetime

# Reloading the rapid_diag bin path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication
from splunklib.binding import HTTPError

# local imports
import logger_manager as log
from rapid_diag_handler_utils import get_endpoint, persistent_handler_wrap_handle
from rapid_diag.util import get_splunkhome_path, build_rapid_diag_timestamp, get_server_name
from rapid_diag.task_handler import TaskHandler
from rapid_diag.task import Task, DEFAULT_OUTPUT_ROOT
from rapid_diag.serializable import Serializable

_LOGGER = log.setup_logging("task_information_endpoint")


class TaskInformationEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)


    def _handle(self, args):
        local = next((arg[1] for arg in args['query'] if arg[0]=='local'), False)
        try:
            local_host = get_server_name(args['system_authtoken'])
        except HTTPError as e:
            _LOGGER.exception('Error trying to retrieve hostname for rapid_diag/task_information', exc_info=e)
            return {'payload':
                        json.dumps({'error':'Error trying to retrieve hostname for rapid_diag/task_information: ' +
                                                    e.reason}), 'status': e.status}
        if not local:
            handler = TaskHandler()
            tasks = handler.list(local_host)
            resp = {"tasks": tasks, "splunk_server": local_host}
            return {'payload': json.dumps(resp), 'status': 200}

        try:
            response = get_endpoint('rapid_diag/task_information', args['system_authtoken'], "")
            _LOGGER.debug("Response: " + str(response))
        except HTTPError as e:
            _LOGGER.exception('Error trying to retrieve rapid_diag/task_information', exc_info=e)
            return {'payload': json.dumps({'error': 'Error trying to retrieve rapid_diag/task_information: ' +
                                                    e.reason}), 'status': e.status}
        for peer_data in response:
            peer_value = json.loads(peer_data['value'])
            splunk_server = peer_value.get('splunk_server')
            if splunk_server == local_host:
                continue
            task_list = peer_value['tasks']
            for task in task_list:
                task = json.loads(json.dumps(task), object_hook=Serializable.jsonDecode)
                output_directory = task.getFinishedOutputDir()
                task_json = Task.RunInfo.getTaskJsonPath(output_directory)
                if not os.path.exists(task_json):
                    os.makedirs(output_directory)
                with open(task_json, 'w+') as f:
                    json.dump(task, f, indent=4, default=Serializable.jsonEncode)

        handler = TaskHandler()
        tasks = handler.list(local_host)
        return {'payload': json.dumps(tasks), 'status': 200}

