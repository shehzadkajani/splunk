# python imports
from __future__ import absolute_import
import os

# local imports
import logger_manager as log
from rapid_diag.util import get_splunkhome_path

# splunk imports
from splunk.clilib import cli_common as cli

# global variables
_LOGGER = log.setup_logging("conf_util")


class RapidDiagConf(object):

    @staticmethod
    def get_collectors_startup_timeout():
        try:
            startup_timeout = os.path.expandvars(cli.getOptConfKeyValue(
                'rapid_diag', 'collectors', 'startup_timeout'))
            return float(startup_timeout)
        except Exception as e:
            _LOGGER.debug("Startup timeout set to 300. Exception during conf reading: {}".format(str(e)))
            return 300

    @staticmethod
    def get_collectors_startup_poll_interval():
        try:
            startup_poll_interval = float(os.path.expandvars(cli.getOptConfKeyValue(
                'rapid_diag', 'collectors', 'startup_poll_interval')))
            return float(startup_poll_interval)
        except Exception as e:
            _LOGGER.debug("Poll interval set to 0.2. Exception during conf reading: {}".format(str(e)))
            return 0.2

    @staticmethod
    def get_threadpool_size_limits():
        try:
            soft_limit = int(os.path.expandvars(cli.getOptConfKeyValue(
                'rapid_diag', 'threadpool', 'threadpool_size_soft_limit')))
            hard_limit = int(os.path.expandvars(cli.getOptConfKeyValue(
                'rapid_diag', 'threadpool', 'threadpool_size_hard_limit')))
            assert(soft_limit > 0 and soft_limit <= hard_limit)
        except Exception as e:
            _LOGGER.debug("Soft limit and hard limit set to 5 and 15 respectively. Exception during conf reading: {}".format(str(e)))
            soft_limit = 5
            hard_limit = 15
        return soft_limit, hard_limit

    @staticmethod
    def get_tools_basepath():
        try:
            basepath = os.path.normpath(os.path.expandvars(cli.getOptConfKeyValue('rapid_diag', 'tools', 'basepath')))
            return basepath
        except Exception as e:
            _LOGGER.debug("Basepath set to None. Exception during conf reading: {}".format(str(e)))
            return None

    @staticmethod
    def get_general_outputpath():
        outputpath = get_splunkhome_path(
            ["var", "run", "splunk", "splunk_rapid_diag"])
        try:
            outputpath = os.path.normpath(os.path.expandvars(cli.getOptConfKeyValue('rapid_diag', 'general', 'outputpath')))
            return outputpath
        except Exception as e:
            _LOGGER.debug("Output path set to default outputpath. Exception during conf reading: {}".format(str(e)))
            return outputpath

