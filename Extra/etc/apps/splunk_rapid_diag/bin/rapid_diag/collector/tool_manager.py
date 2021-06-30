# python imports
from __future__ import absolute_import
import os
import json
import threading

# local imports
import logger_manager as log
from rapid_diag.util import get_splunkhome_path
from rapid_diag.conf_util import RapidDiagConf
from rapid_diag.serializable import Serializable

_LOGGER = log.setup_logging("tool_manager")

DEFAULT_BASE_TOOLPATH = os.path.normpath(get_splunkhome_path(['etc', 'apps', 'splunk_rapid_diag', 'bin', 'tools']))


class ToolAvailabilityManager(object):
    def __init__(self):
        self.lock = threading.Lock()

        tool_manager_path = get_splunkhome_path(
            ["var", "run", "splunk", "splunk_rapid_diag"])
        self.tools = {}
        if not os.path.isdir(tool_manager_path):
            os.makedirs(tool_manager_path)
        self.available_tool_path = os.path.join(
            tool_manager_path, 'available_tools.json')
        try:
            if os.path.isfile(self.available_tool_path):
                with open(self.available_tool_path, 'r') as f:
                    self.tools = json.load(f)
        except Exception as e:
            _LOGGER.exception("Error loading '" + self.available_tool_path + "': " + str(e))

    def set_available(self, utility_name, status):
        with self.lock:
            if utility_name in self.tools and self.tools[utility_name] == status:
                return
            self.tools[utility_name] = status
            with open(self.available_tool_path, 'w+') as f:
                json.dump(self.tools, f, default=Serializable.jsonEncode)

    def is_available(self, utility_name):
        with self.lock:
            is_utility_available = True if (utility_name in self.tools and self.tools[utility_name] == True) else False
            return is_utility_available

    def get_tool_message(self, utility_name):
        # get_tool_message should be called after set_available because if key is not available it will return KeyError
        with self.lock:
            assert(os.path.isfile(self.available_tool_path))
            return self.tools[utility_name]

    @staticmethod
    def get_tool_paths():
        """creates a list of a path which should be explored for finding utility

        NOTE:
        * if toolpath is not updated in `rapid_diag.conf` it will take '$SPLUNK_HOME/etc/apps/splunk_rapid_diag/bin/tools' as default path
        * We are using a list instead of a set because set in an unordered collection due to which insertion will change the order of elements.
        * In case of a set, Indexes of the path will be different(because sets are unordered collection) and if we have multiple versions of utility tools then we can't be sure which version is invoked by the program.
        * In case of a list, there should be duplications only if the PATH variable contains duplicate values
        * `baseToolpath` will have have maximum priority.

        Returns
        -------
        [list]
            list of directory paths
        """

        paths = os.environ.get("PATH").split(os.pathsep)
        baseToolpath = os.path.normpath(os.path.join(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), 'tools'))

        try:
            confPath = RapidDiagConf.get_tools_basepath()
            if confPath and confPath != DEFAULT_BASE_TOOLPATH:
                baseToolpath = confPath
        except:
            pass
        paths.insert(0, baseToolpath)

        return paths

    @staticmethod
    def find(program):
        """finds the utilites in system and app directories.

        Verifies following:
        1. the utility path
        2. execute permission

        Parameters
        ----------
        program : string
            name of utility

        Returns
        -------
        ToolManagerOutput
            return object with `toolpath` or `error_message`
        """

        result = None
        paths = ToolAvailabilityManager.get_tool_paths()
        for path in paths:
            f = os.path.join(path, program)
            if os.path.exists(f) and os.path.isfile(f):
                # a good match should be returned straight away
                if os.access(f, os.X_OK):
                    # in Windows X_OK is meaningless, but we're only checking files with executable extensions, which is the Windows way of saying X_OK, so this works fine
                    return ToolManagerOutput(f, None)
                # if we don't find any good binary, report permission error for the first bad match
                elif result is None:
                    result = ToolManagerOutput(None, program + " doesn't have execute permission for the current user.")
        # and if we find nothing, we report that too
        if result is None:
            result = ToolManagerOutput(None, "Could not detect `" + str(program) + "`")
        return result


class ToolManagerOutput(object):
    def __init__(self, toolpath=None, error_message=None):
        self.toolpath = toolpath
        self.error_message = error_message

    def __repr__(self):
        return 'ToolManagerOutput(%r, %r)' % (self.toolpath, self.error_message)
