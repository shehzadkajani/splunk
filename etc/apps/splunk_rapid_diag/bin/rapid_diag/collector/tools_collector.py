from __future__ import absolute_import
import sys
import subprocess
from time import sleep

import logger_manager as log
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult
from rapid_diag.abstractstatic import abstractstatic
from rapid_diag.conf_util import RapidDiagConf

_LOGGER = log.setup_logging("tools_collector")

IS_LINUX = sys.platform.startswith('linux')
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008


class ToolsCollector(object):

    def __init__(self, collection_time=None, valid_return_code=None):
        self.collection_time = int(collection_time) if collection_time else RapidDiagConf.get_collectors_startup_timeout()
        self.valid_return_code = valid_return_code if valid_return_code else [0]

    @abstractstatic
    def get_tool_name(platform=sys.platform):
        """
        Returns the utility name depending on the platform.
        """
        pass

    @abstractstatic
    def tool_missing():
        """
        Check the utility to run the collector is available or not.
        """
        pass

    def run(self, command, output, error, poll_period=RapidDiagConf.get_collectors_startup_poll_interval()):
        if IS_LINUX:
            process = subprocess.Popen(
                command, stdout=output, stderr=error)
        else:
            process = subprocess.Popen(
                command, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, stdout=output, stderr=error)

        returnCode = self.__wait_for_completion(process, self.collection_time, poll_period)
        _LOGGER.debug("returnCode : " + str(returnCode))

        if returnCode == None:
            self.__terminate(process)

        if returnCode not in self.valid_return_code:
            return CollectorResult.Failure("Error occured for collector " + str(self.tool_name) + " while running `" +
                                        " ".join(command) + "`\nProcess finished with " +
                                        "code=" + str(process.returncode) , _LOGGER)    

        if self.get_state() == Collector.State.ABORTING:
            return CollectorResult.Aborted(self.tool_name + " aborted by user", _LOGGER)
        
        return CollectorResult.Success(self.tool_name + " execution completed successfully", _LOGGER)


    def __wait_for_completion(self, process, collection_time, poll_period):
        for i in range(0, int(collection_time / poll_period)):
            sleep(poll_period)
            returnCode = process.poll()
            _LOGGER.debug('Polling returnCode for ' + str(self.tool_name) + ' i = ' +
                          str(i) + ' -- ' + str(returnCode))
            if returnCode is not None or self.get_state() == Collector.State.ABORTING:
                return returnCode
        return None

    def __terminate(self, process, command=None):
        _LOGGER.info("Terminating collector " + self.tool_name )
        if IS_LINUX:
            process.terminate()
        else:
            command = command if command is not None else ['taskkill', '/T', '/PID', str(process.pid)]
            subprocess.call(command)
        
        return_code = self.__wait_for_completion(process, 3, 0.1)
        if return_code == None:
            self.__kill(process)

    def __kill(self, process):
        _LOGGER.info("Force terminating collector " + self.tool_name )
        if IS_LINUX:
            process.kill()
        else:
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
        _LOGGER.info('Force killed collector to avoid excessive collection')
