# python imports
import os
import sys
import json

# Reloading the rapid_diag bin path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication
from splunklib.binding import HTTPError

# local imports
import logger_manager as log
from rapid_diag_handler_utils import get_endpoint, persistent_handler_wrap_handle
from rapid_diag.util import get_log_files, get_server_name

_LOGGER = log.setup_logging("log_file_list_endpoint")


class LogFileListEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        peers_string = next((arg[1] for arg in args['query'] if arg[0] == 'peers'), '[]')
        peers = json.loads(peers_string)
        if not peers:
            log_files = get_log_files()
        else:
            endpoint_data = get_endpoint('rapid_diag/get_log_files', args['system_authtoken'])
            log_files_set = set()
            for result in endpoint_data:
                if result.get('splunk_server') not in peers:
                    continue
                log_files_set.update(json.loads(result.get('value')).values())
            log_files = list(log_files_set)
        _LOGGER.debug("List of log files: " + str(log_files))
        log_files = {idx: val for idx, val in enumerate(sorted(log_files))}
        return {'payload': json.dumps(log_files), 'status': 200}

