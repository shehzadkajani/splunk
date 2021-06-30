from __future__ import print_function, absolute_import
import sys
import os
import re
import threading
import subprocess
import socket
import tempfile
import shutil

# if collector is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

# local imports
from splunklib import six
import logger_manager as log
from rapid_diag.collector.type import Type
from rapid_diag.collector.resource import Resource
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.tools_collector import ToolsCollector
from rapid_diag.collector.collector_result import CollectorResult
from rapid_diag.collector.tool_manager import ToolAvailabilityManager
from rapid_diag.util import build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals

_LOGGER = log.setup_logging("network_packet")
IS_LINUX = sys.platform.startswith('linux')


class NetworkPacket(Collector, ToolsCollector, Serializable):
    """ RapidDiag collector allows to collect network packets """

    def __init__(self, collection_time, ip_address=None, port=None, state=Collector.State.WAITING):
        Collector.__init__(self)
        ToolsCollector.__init__(self, collection_time=collection_time, valid_return_code=[0, None])
        self.ip_address = ip_address
        self.port = port
        self.state = state
        self.tool_name = self.get_tool_name()
        self.tool_manager_output = ToolAvailabilityManager.find(self.tool_name)

    @staticmethod
    def get_tool_name():
        return ("tcpdump" if IS_LINUX else "netsh.exe")

    @staticmethod
    def tool_missing():
        utility_name = NetworkPacket.get_tool_name()
        tool_manager = SessionGlobals.get_tool_availability_manager()
        is_avail = tool_manager.is_available(utility_name)
        if is_avail:
            return None
        tempDir = tempfile.mkdtemp()
        try:
            dummy_obj = NetworkPacket(2)
            _ = dummy_obj.collect(Collector.RunContext(tempDir, '', None))
            message = tool_manager.get_tool_message(utility_name)
            message = None if message == True else message
        finally:
            shutil.rmtree(tempDir, True)
        return message

    def getType(self):
        return Type.CONTINUOUS

    def get_required_resources(self):
        if not IS_LINUX:
            return [Resource('netsh')]
        return [Resource('tcpdump')]

    def __repr__(self):
        return "Network Packet(Collection Time: %r, IP Address: %r, Port: %r)" % (self.collection_time, self.ip_address, self.port)

    def toJsonObj(self):
        return {
            'collection_time': self.collection_time,
            'ip_address': self.ip_address,
            'port': self.port,
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def check_ip_address(ip_addr):
        valid_ip4 = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
        valid_ip6 = "^((([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:)\
            {1,4}(:[0-9a-fA-F]\
            {1,4}){1,3}|([0-9a-fA-F]{1,4}:)\
            {1,3}(:[0-9a-fA-F]\
            {1,4}){1,4}|([0-9a-fA-F]{1,4}:)\
            {1,2}(:[0-9a-fA-F]\
            {1,4}){1,5}|[0-9a-fA-F]\
            {1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4})\
            {0,4}%[0-9a-zA-Z]\
            {1,}|::(ffff(:0{1,4})\
            {0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9])\
            {0,1}[0-9])|([0-9a-fA-F]{1,4}:)\
            {1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.)\
            {3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9])\
            {0,1}[0-9])))$"

        if not re.match(valid_ip4, str(ip_addr)) and not re.match(valid_ip6, str(ip_addr)):
            raise ValueError("ip_address: Please enter valid IP Address.")

    @staticmethod
    def validateJson(obj):
        data_types = {"collection_time": (float, int), "ip_address": (six.text_type, type(None)), "port" : (int, type(None))}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        value_range = {"collection_time": [10, Collector.MAX_TIME], "port": [1,65535]}
        for field in list(filter(lambda x: x in obj.keys(), value_range.keys())):
            Serializable.check_value_in_range(obj[field], value_range[field], field)

        if obj.get('ip_address') is not None:
            NetworkPacket.check_ip_address(obj.get('ip_address'))
        
    @staticmethod
    def fromJsonObj(obj):
        return NetworkPacket(obj['collection_time'], obj.get('ip_address'), obj.get('port'), Collector.State.get_status_code(obj.get("state")))

    def _collect_impl(self, runContext):
        tool_manager = SessionGlobals.get_tool_availability_manager()
        if self.tool_manager_output.error_message is not None:
            status = CollectorResult.Failure(self.tool_manager_output.error_message, _LOGGER)
        else:
            self.promote_state(Collector.State.COLLECTING, runContext.stateChangeObservers)
            collectFun = self._collect_linux if IS_LINUX else self._collect_windows
            status = collectFun(runContext.outputDir, runContext.suffix)
        tool_worked = status.isSuccess() or self.get_state() == Collector.State.ABORTING
        tool_manager.set_available(self.tool_name, True if tool_worked else self.tool_manager_output.error_message)
        return status

    def _collect_linux(self, outputDir, suffix):
        """For Linux, collects network packets from destination ip address and port using tcpdump utility."""
        _LOGGER.info('Starting NetworkPacket collector: with ip_address="' + str(self.ip_address) +
                     '" port="' + str(self.port) + '" outputDir="' + outputDir + '" suffix="' + suffix + '"')
        _LOGGER.debug("Task assigned to thread: " +
                      str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: " + str(os.getpid()))

        fname = os.path.join(outputDir, 'tcpdump_' + (str(self.ip_address) if self.ip_address is not None else "All") + "_" + (str(self.port) if self.port is not None else "All") + suffix)

        command = [self.tool_manager_output.toolpath, '-i', 'any']
        if outputDir:
            command += ['-w', fname + '.pcap']
        filters = ''
        if self.ip_address is not None:
            filters = ' dst host ' + str(self.ip_address)
        if self.port is not None:
            if filters:
                filters += ' and'
            filters += ' dst port ' + str(self.port)
        command.append(filters)
        _LOGGER.debug('Running `' + ' '.join(command)+'`')
        with open(os.devnull, 'w') as output, open(fname + ".err", "a+") as error:
            try:
                result = self.run(command, output, error, poll_period=0.1)
            except EnvironmentError as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name) +
                                                ', please confirm you have the ' + str(self.tool_name) + ' package ' +
                                                'installed in your system and that the ' + str(self.tool_name) +
                                                ' command is available -- path=' + os.getenv('PATH'), _LOGGER)
            except Exception as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name), _LOGGER)

        return result     
        
    def _collect_windows(self, outputDir, suffix):
        """For Windows, collects network packets from destination ip address using netsh utility."""
        _LOGGER.info('Starting NetworkPacket collector, outputDir="' +
                     outputDir + '" suffix="' + suffix + '"' + '" ip_address="' + str(self.ip_address) + '"')
        _LOGGER.debug("Task assigned to thread: " +
                      str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        command = [self.tool_manager_output.toolpath, 'trace', 'start', 'capture=yes',
                    'Ethernet.Type=(IPv4,IPv6)']
        fname = os.path.join(outputDir, 'netsh_' + (str(self.ip_address) if self.ip_address is not None else "All") + "_" + (str(self.port) if self.port is not None else "All") + suffix)
        if outputDir:
            command.append('tracefile=' + fname + '.etl')
        if self.ip_address is not None:
            filters = ('IPv4' if self.is_ipv4() else 'IPv6') + \
                '.DestinationAddress=' + str(self.ip_address)
            command.append(filters)
        _LOGGER.debug('Running `' + ' '.join(command)+'`')  
        
        with open(os.devnull, 'w') as output, open(fname + ".err", "a+") as error:
            try:
                result = self.run(command, output, error, poll_period=0.1)
            except EnvironmentError as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name) +
                                                ', please confirm you have the ' + str(self.tool_name) + ' package ' +
                                                'installed in your system and that the ' + str(self.tool_name) +
                                                ' command is available -- path=' + os.getenv('PATH'), _LOGGER)
            except Exception as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name), _LOGGER)

            if result.isFailure():
                return result

            self.wait_for_state(Collector.State.ABORTED, self.collection_time)
            
            self._stop()

            return result

    def _stop(self):
        """Terminates netsh collection process."""
        _LOGGER.info('Stopping netsh trace...')
        command = ['netsh', 'trace', 'stop']
        _LOGGER.debug('Stopping netsh trace `' + ' '.join(command)+'`')
        subprocess.call(command)

    def cleanup(self, **kwargs):
        self._stop()

    def is_ipv4(self):
        """Checks IP type is IPv4 (True) or IPv6 (False)."""
        try:
            socket.inet_aton(self.ip_address)
            _LOGGER.debug('IP Address (IPv4) ' + self.ip_address)
            return True
        except socket.error:
            _LOGGER.debug('IP Address (IPv6) ' + self.ip_address)
            return False


Serializable.register(NetworkPacket)
