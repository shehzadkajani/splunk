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
from rapid_diag.util import get_server_name
from rapid_diag.session_globals import SessionGlobals

_LOGGER = log.setup_logging("process_list_endpoint")


class ProcessListEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        peers_string = next((arg[1] for arg in args['query'] if arg[0] == 'peers'), '[]')
        peers = json.loads(peers_string)
        if not peers:
            proc_data = json.dumps(SessionGlobals.get_process_lister().get_ui_process_list())
        else:
            if len(peers) > 1 and peers[0] == get_server_name(args['system_authtoken']):
                peers = peers[1:]
            peer_data = get_endpoint('rapid_diag/get_process_info', args['system_authtoken'], peers[0])
            proc_data = peer_data[0].get('value')
        _LOGGER.debug("Process Data: " + str(proc_data))
        return {'payload': proc_data, 'status': 200}


