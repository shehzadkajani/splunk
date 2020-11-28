# python imports
from __future__ import absolute_import
import re
import os
import csv
import sys
import time
import json
import threading
from splunklib import six

# local imports
from rapid_diag.util import get_splunkhome_path
from rapid_diag.serializable import Serializable
from rapid_diag.process_match import ProcessMatch

# global variables
PPID_REX = re.compile(r"^PPid:\s*(\d+)$")
NAME_REX = re.compile(r"^Name:\s*(.+)$")
SID_REX = re.compile(r"\s--id=(\S+)")

IS_LINUX = sys.platform.startswith('linux')


class ProcessNotFound(Exception):
    """Raised when PID is not found in the system"""
    pass

class Process(ProcessMatch, Serializable):
    def __init__(self, name, pid, ppid, args, process_type):
        self.name = name
        self.pid = pid
        self.ppid = ppid
        self.args = args
        self.process_type = process_type

    def __str__(self):
        return str(self.toJsonObj())

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    def may_match(self, other):
        if self.__class__ != other.__class__ or self.process_type != other.process_type: # never match processes of different types
            return False
        return self.name == other.name

    def __repr__(self):
        return "%s (%r), Process Type: %s" % (self.name, self.pid, self.process_type)

    def toJsonObj(self):
        return {
            'name': self.name,
            'pid': self.pid,
            'ppid': self.ppid,
            'args': self.args,
            'process_type': self.process_type,
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"name": (six.text_type,), "pid": (int,), "ppid": (int,), "args": (six.text_type,), "process_type": (six.text_type,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        # In windows max PID value is DWORD which is having lenght from [-2^32, 2^32-1]
        # In linux PID_MAX_LIMIT is 2^22 for 64bit machines
        value_range = {"pid": [0, 4294967295], "ppid": [0, 4294967295]}
        for field in list(filter(lambda x: x in obj.keys(), value_range.keys())):
            Serializable.check_value_in_range(obj[field], value_range[field], field) 

        string_value = ["name", "process_type"]
        for field in list(filter(lambda x: x in obj.keys(), string_value)):
            Serializable.check_string_value(obj[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return Process(obj['name'], obj['pid'], obj['ppid'], obj['args'], obj['process_type'])

Serializable.register(Process)

class SearchProcess(ProcessMatch, Serializable):
    def __init__(self, process, root_sid, label, ppc_app, ppc_user, search, owner=None, app=None):
        self.process = process
        self.root_sid = root_sid
        self.savedsearch_name = label
        self.running_app = ppc_app
        self.running_user = ppc_user
        self.search = search
        self.owning_user = owner
        self.owning_app = app

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        process_dict = self.toJsonObj()
        process_dict.update({'process': process_dict['process'].toJsonObj()})
        return str(process_dict)

    @staticmethod
    def load_from_disk(process, sid):
        search_path = get_splunkhome_path(['var', 'run', 'splunk', 'dispatch', sid, 'info.csv'])
        with open(search_path, 'r') as f:
            dict_reader = csv.DictReader(f)
            search_info = next(dict_reader)
        try:
            saved_search_info = json.loads(search_info["savedsearch_label"])
            return SearchProcess(process, search_info["_root_sid"], search_info["label"], search_info["_ppc.app"], search_info["_ppc.user"], \
                    search_info["_search"], saved_search_info["owner"], saved_search_info["app"])
        except:
            return SearchProcess(process, search_info["_root_sid"], search_info["label"], search_info["_ppc.app"], search_info["_ppc.user"], \
                    search_info["_search"])


    def may_match(self, other):
        if not self.process.may_match(other.process):
            return False
        return self.root_sid==other.root_sid or (self.savedsearch_name!="" and self.savedsearch_name==other.savedsearch_name) or self.search==other.search

    def __repr__(self):
        return "%r, Search: %s, Saved search name: %s, Root SID: %s" % (self.process, self.search, self.savedsearch_name, self.root_sid)

    def toJsonObj(self):
        return {
            'process': self.process,
            'root_sid': self.root_sid,
            'savedsearch_name': self.savedsearch_name,
            'running_app': self.running_app,
            'running_user': self.running_user,
            'search': self.search,
            'owning_user': self.owning_user,
            'owning_app': self.owning_app,
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"process": (object,), "root_sid": (six.text_type,), "savedsearch_name": (six.text_type,), "running_app": (six.text_type,),"running_user": (six.text_type,), "search": (six.text_type,), "owning_user": (six.text_type, type(None)), "owning_app": (six.text_type, type(None))}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        string_value = ["root_sid", "savedsearch_name", "running_app", "running_user"]
        for field in list(filter(lambda x: x in obj.keys(), string_value)):
            Serializable.check_string_value(obj[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return SearchProcess(obj['process'], obj['root_sid'], obj['savedsearch_name'], obj['running_app'], obj['running_user'], obj['search'], obj.get('owning_user'), obj.get('owning_app'))

Serializable.register(SearchProcess)

class ProcessLister(object):
    CACHE_TTL = 2

    def __init__(self):
        self.read_lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.listing = None # DO NOT ACCESS DIRECTLY, use `get_process_listing()`
        self.refresh_time = 0.
        self.refreshing = False

    @staticmethod
    def build_process(name, pid, ppid, args):
        args = ' '.join(args)
        process_type = 'other'
        if name and args:
            if name == 'splunkd':
                if 'search' in args:
                    match = re.search(SID_REX, args)
                    if match:
                        return SearchProcess.load_from_disk(Process(name, pid, ppid, args, 'splunk search'), match.group(1))
                    else:
                        process_type = 'splunk search runner'
                elif 'process-runner' in args:
                    process_type = 'splunk process-runner'
                elif (' -p ' in args and 'start' in args) or args.endswith(' service'):
                    process_type = 'splunkd server'
                elif 'fsck' in args or 'recover-metadata' in args or 'cluster_thing' in args:
                    process_type = 'splunk index service'
                elif 'instrument-resource-usage' in args:
                    process_type = 'splunk scripted input'
            elif name.startswith('python'):
                if ('appserver' in args and 'mrsparkle' in args and 'root.py' in args) or args.startswith('splunkweb'):
                    process_type = 'splunk web'
            elif name == 'mongod':
                if os.path.join('var', 'lib', 'splunk', 'kvstore', 'mongo') in args:
                    process_type = 'splunk kvstore'
        return Process(name, pid, ppid, args, process_type)
    
    @staticmethod
    def build_process_from_pid(pid):
        try:
            if IS_LINUX:
                return ProcessLister._build_process_linux(pid)
            return ProcessLister._build_process_windows(pid)
        except:
            raise ProcessNotFound('Unable to find a matching process for pid: {!s}'.format(pid))

    @staticmethod
    def _build_process_windows(pid):
        import wmi
        import pythoncom

        pythoncom.CoInitialize()
        wmi_obj = wmi.WMI()

        process = wmi_obj.Win32_Process(processid=pid)[0]
        name = process.Name.split(".exe")[0]
        pid = process.ProcessId
        ppid = process.ParentProcessId
        args = process.CommandLine.split('\0') if process.CommandLine else [str(process.CommandLine)]

        return ProcessLister.build_process(name, int(pid), int(ppid), args)
    
    @staticmethod
    def get_process_listing_windows():
        import wmi
        import pythoncom

        pythoncom.CoInitialize()

        wmi_obj = wmi.WMI()
        listing = []
        for process in wmi_obj.Win32_Process():
            try:
                process = ProcessLister.build_process_from_pid(process.ProcessId)
                listing.append(process)
            except IndexError:
                continue
            except ProcessNotFound:
                continue

        return listing

    @staticmethod
    def _build_process_linux(pid):
        with open(os.path.join('/proc', str(pid), 'cmdline'), 'r') as proc_cmdline:
            args = [line for line in proc_cmdline.read().split('\0') if line]

        with open(os.path.join('/proc', str(pid), 'status'), 'r') as proc_status:
            ppid = None
            name = None
            
            for line in proc_status:
                if re.match(PPID_REX, line):
                    ppid = line.split(":")[1].strip()
                if re.match(NAME_REX, line):
                    name = line.split(":")[1].strip()
                if ppid and name:
                    break
            if ppid is None:
                ppid = "1"
            if name is None:
                name = args[0]
        return ProcessLister.build_process(name, int(pid), int(ppid), args)

    @staticmethod
    def get_process_listing_linux():
        listing = []
        for pid in [pid for pid in os.listdir('/proc') if pid.isdigit()]:
            try:
                process = ProcessLister.build_process_from_pid(pid)
                listing.append(process)
            except IOError:
                continue
            except ProcessNotFound:
                continue
        return listing

    def get_process_listing(self, force_refresh=False):
        with self.read_lock:
            if self.listing and not force_refresh:
                now = time.time()
                age = now - self.refresh_time
                if age < ProcessLister.CACHE_TTL or self.refreshing:
                    return self.listing[:] # return copy to avoid races
            self.refreshing = True
        with self.refresh_lock: # this second lock is meant to prevent cache stampedes
            if self.listing and not force_refresh:
                # the only way we got here is if previously `self.listing` evaluated to False -- that means we'd better return
                # whatever the age, because if extracting the list takes longer than TTL we don't want to keep doing it over and over
                return self.listing[:]

            if IS_LINUX:
                listing = ProcessLister.get_process_listing_linux()
            else:
                listing = ProcessLister.get_process_listing_windows()

            with self.read_lock:
                self.listing = listing
                self.refresh_time = time.time()
                self.refreshing = False
            return self.listing[:]

    def get_best_running_match(self, process):
        listing = self.get_process_listing()
        best = None
        best_score = 0
        for proc in listing:
            try:
                if proc.may_match(process):
                    score = proc.get_match_score(process)
                    if score > best_score:
                        best = proc
                        best_score = score
            except:
                continue
        return best

    def get_ui_process_list(self):
        process_list = []
        for proc in self.get_process_listing():
            process_list.append(
                json.dumps(proc, default=self.json_encoder)
            )
        process_dict = { i : process_list[i] for i in range(0, len(process_list)) }
        
        return process_dict

    @staticmethod
    def json_decoder(json_dict):
        if "process" in json_dict:
            json_dict["process"] = Process.fromJsonObj(json_dict["process"])
            return SearchProcess.fromJsonObj(json_dict)
        else:
            return Process.fromJsonObj(json_dict)

    def json_encoder(self, obj):
        if hasattr(obj, 'toJsonObj'):
            return obj.toJsonObj()
        raise TypeError('Can\'t serialize "{!s}"={!s}'.format(type(obj), obj))
