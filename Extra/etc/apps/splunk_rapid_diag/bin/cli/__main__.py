#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# python imports
import argparse
from argparse import SUPPRESS
import sys
import os
import errno
import signal 

# get real path if it's a symlink
try:
    module_file = os.readlink(__file__)
except:
    module_file = __file__

module_root = os.path.dirname(__file__)
if not os.path.isabs(module_file):
    module_path = os.path.normpath(os.path.join(module_root, module_file))
else:
    module_path = module_file

sys.path.append(os.path.dirname(os.path.dirname(module_path)))

# only one local import here
from cli.cli_error_code import ErrorCodes

# global CLI signal handler - for early bailouts... 
def cli_startup_signal_handler(sig, frame):
    sys.stderr.write("\rERROR: Action aborted\n")
    sys.stderr.flush()
    sys.exit(ErrorCodes.ACTION_ABORTED)

# set the signal before doing anything else
signal.signal(signal.SIGINT, cli_startup_signal_handler)


# local imports
from rapid_diag_cli import RapidDiagCLI
from rapid_diag.util import get_splunkhome_path, build_rapid_diag_timestamp, bytes_to_str

def argparse_check_dir(directory):
    full = os.path.abspath(directory)
    if os.path.isdir(full):
        return full
    raise argparse.ArgumentError(None, "Directory '%s' does not exist." % directory)

def argparse_add_default_args(parser):
    """ Add default CLI arguments.
        Those arguments are used by every collector.
    """
    parser.add_argument('output_dir', metavar='output-dir', default=None,
            help='Output directory path. Confirm there is adequate available disk space.')
    parser.add_argument('--suffix', dest='suffix', default='_' + build_rapid_diag_timestamp(), 
            help='Collection output filename suffix. The default is a timestamp.')

def argparse_add_standard_collector(name, parser):
    """ Add collector of a given 'name'.
    """
    collector_parser = parser.add_parser(
            name, help='Execute ' + name + ' collection')
    argparse_add_default_args(collector_parser)
    return collector_parser

def argparse_add_process_arg(parser):
    """ Used for all collectors that operate on a process
    """
    parser.add_argument('--pid', default=0,
            help='The process id to monitor. If fuzzy matching should be used - set this to 0.')
    parser.add_argument('--ppid', default=0, help='The parent process id to monitor.')
    parser.add_argument('--name', default="splunkd", help='The name of the process to monitor. Defaults to \'splunkd\'.')
    parser.add_argument('--args', default="splunkd service", help='The command line arguments of the process to monitor.')

def argparse_add_collection_time_arg(parser):
    """ Used for all collectors that have collection time arg.
    """
    parser.add_argument('--collection-time', dest='collection_time', default=600, 
            help='The run time for the collection. Default is 600 seconds.')

def argparse_add_ip_port_args(parser):
    """ Used for all collectors that need IP and port
    """
    parser.add_argument('--ip-address', dest='ip_address', default=None, 
            help='The IP Address to monitor. If unset, all IP addresses will be monitored.')
    parser.add_argument('--port', dest='port', default=None, 
            help='The network port to monitor. If unset, all ports will be monitored.')

def argparse_add_collection_query_arg(parser):
    """ Used for all collectors that need search query
    """
    parser.add_argument('search_query', metavar='search-query', default=None, help='The search query to execute.')


def argparse_add_collectors(parser):
    """ Helper function that adds collectors subparsers - since we use it in different modes.
    """

    coll_group = parser.add_subparsers(
            dest="collector", 
            help="Choose one collector to be executed from the list.")

    # these collectors have only default args - so let's just be minimalistic here
    col_list = ["ps", "diag", "netstat"]
    list(map(lambda x:argparse_add_standard_collector(x, coll_group), col_list))
  
    # collectors with PID
    pstack_collector = argparse_add_standard_collector("pstack", coll_group)
    argparse_add_process_arg(pstack_collector)

    lsof_collector = argparse_add_standard_collector("lsof", coll_group)
    argparse_add_process_arg(lsof_collector)

    strace_collector = argparse_add_standard_collector("strace", coll_group)
    argparse_add_process_arg(strace_collector)

    # collectors with collection time
    argparse_add_collection_time_arg(strace_collector)

    iostat_collector = argparse_add_standard_collector("iostat", coll_group)
    argparse_add_collection_time_arg(iostat_collector)

    tcpdump_collector = argparse_add_standard_collector("tcpdump", coll_group)
    argparse_add_collection_time_arg(tcpdump_collector)

    # collectors with ip/port
    argparse_add_ip_port_args(tcpdump_collector)

    # collectors with search query
    search_collector = argparse_add_standard_collector("search", coll_group)
    argparse_add_collection_query_arg(search_collector)

def run(args):
    rapid_diag_parser = argparse.ArgumentParser(
        description='''
DESCRIPTION:
        
        The Splunk RapidDiag app collects diagnostic data on Splunk platform deployments that run on Linux and Windows
         operating systems for the purposes of analysis by the Splunk Support and Engineering teams.

        The app provides command-line scripts and a web interface for various diagnostic data collection tasks:

        - Stack dumps: pstacks, eu-stacks, or procdump;
        - System call traces: strace or procmon; 
        - Splunk diag;
        - Rest endpoint outputs: ( \`\`|rest search\`\` exports); and
        - Network packet dumps: tcpdump or netsh.
        - I/O operations: logman or iostat;
        - Network statistics and network connections: netsh; and
        - Process information: ps, lsof, or handle64.

        Splunk RapidDiag also offers automatic data collection based on triggers – for example, start collecting data
        when Splunk platform processes write certain keywords to a specific log file, or when system-wide memory usage crosses a threshold.

        Please inspect available COMMANDS for further details.

        NOTE: All collections are executed on local machine only.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True
    )

    # MAIN PARSER
    subparsers = rapid_diag_parser.add_subparsers(
        title="RAPID-DIAG COMMANDS",
        dest="mode", prog="rapidDiag")

    # TEMPLATES
    templates_parser = subparsers.add_parser(
        'templates', help='Execute action on templates.',
        description='Templates are predefined collection tasks that target specific issues.')

    templates_subparsers = templates_parser.add_subparsers(dest="action") 

    templates_subparsers.add_parser(
        'list', help="List pre-built tasks for the RapidDiag app.",
        description="Lists pre-built tasks for the RapidDiag app."
                     " Predefined tasks are available in the SampleTasks directory within the app.")

    exec_parser = templates_subparsers.add_parser(
        'run', help='Execute a task with a given task ID.',
        description='Execute the task with the given task ID. If RapidDiag cannot find a file within the'
                    ' SampleTasks directory with a matching task ID, it returns a "task not found" error.'
                    '  Please use "list" command to see available tasks with their corresponding tasks IDs.')
    exec_parser.add_argument('task_id', type=str, help="Task ID of the template to be executed.")

    add_parser = templates_subparsers.add_parser('add',
        help="Add new json task file to the templates.",    
        description="Copies the collection json file to the SampleTasks directory."
                    " Fails if a template with the same name already exists. To override this, use -f flag.")
    add_parser.add_argument('file', type=str, help='Name of the json task file to be added as a template.')
    add_parser.add_argument(
        '--name', '-n', type=str, help="Custom task name (if not specified - current file name is used).")
    add_parser.add_argument(
        '--force', '-f', default=False, action='store_true', help="If set, overrides existing template. Otherwise error"
        " message will be shown if a template with the same name already exists.")

    # INDIVIDUAL COLLECTORS
    collect_parser = subparsers.add_parser(
        'collect', help='Execute specific collector once.',
        description='In "collect" mode given collector will be executed once. In general this option is fine for '
                    ' a one-off collection (if needed) or for collectors where running time can be controlled.')
    argparse_add_collectors(collect_parser)

    # PERIODIC COLLECTION
    periodic_parser = subparsers.add_parser(
        'periodic-collect', help='Execute specific collector periodically.',
        description='In "periodic-collect" mode given collector will be executed periodically - N times with specified '
                    ' delay between executions. This option is most common for pstack/netstat and similar sample-based '
                    ' data.')
    periodic_parser.add_argument('--sample-count', dest='sample_count', default=600, 
        help='Number of samples to be gathered. Defaults to 600.')
    periodic_parser.add_argument('--interval', dest='interval', default=1, 
        help='The interval time, in seconds, between each two samples. Defaults to 1.')
    argparse_add_collectors(periodic_parser)

    # RESOURCE MONITOR
    resorce_mon_parser = subparsers.add_parser(
        'resource-monitor', 
        help='Execute given collector when specific resource threshold is exceeded.',
        description='In "resource-monitor" mode given collector will be executed once the threshold of specified'
                    ' resource is reached.')
    resorce_mon_parser.add_argument('--cpu', dest='cpu', metavar='CPU_THRESHOLD',
        help='Threshold value (percentage) for the cpu usage.')
    resorce_mon_parser.add_argument('--physical_memory', '-pm', dest='physical_memory',
        metavar='PHYSICAL_MEMORY_THRESHOLD',
        help='Threshold value for physical memory usage, in kilobytes.')
    resorce_mon_parser.add_argument('--virtual_memory', '-vm', dest='virtual_memory',
        metavar='VIRTUAL_MEMORY_THRESHOLD',
        help='Threshold value for virtual memory usage, in kilobytes.')
    resorce_mon_parser.add_argument('--inverted', '-I', dest='invert', default=False, action='store_true',
        help='If specified, inverts the logic of the threshold i.e. trigger will happen'
             ' when value drops below instead.')
    argparse_add_collectors(resorce_mon_parser)

    # LOG MONITOR
    log_mon_parser = subparsers.add_parser(
        'log-monitor', help='Execute given collector when specific regex is matched.',
        description='In "log-monitor" mode given collector will be executed once the given regex is matched '
                    ' in a specified log file (found in $SPLUNK_HOME/var/log/* and/or subfolders).')
    log_mon_parser.add_argument('--log-file', '-f', dest='log_file', default="splunkd.log", 
        help='Name of the log file to monitor. Defaults to splunkd.log.')
    log_mon_parser.add_argument('regex',
        help='Regex to be matched in the monitored log file that triggers collection.')
    argparse_add_collectors(log_mon_parser)

    # SEARCH DEBUG
    search_debug_parser = subparsers.add_parser(
        'search-debug', help='Execute given collector when search process is matched.',
        description='In "search-debug" mode given collector will be executed once the search process is matched.')
    search_debug_parser.add_argument('regex',
        help='Regex to be matched in the search\'s SPL string that triggers collection.')
    argparse_add_collectors(search_debug_parser)

    try:
        args = rapid_diag_parser.parse_args()

        # ADDING SPECIALIZED ARGS CHECKS HERE
        # 1) Make sure resource monitor got at least one arg to work with
        if args.mode == "resource-monitor" and not (args.cpu or args.physical_memory or args.virtual_memory):
            resorce_mon_parser.error("At least one of the resources: CPU, PHYSICAL_MEMORY or VIRTUAL_MEMORY must be"
                                     " specified.")

        if args.mode == "templates":
            if args.action == "run":
                return RapidDiagCLI().run_task_template(args)
            elif args.action == "add":
                return RapidDiagCLI().json_upload(args)
            else: # must be "list"
                return RapidDiagCLI().task_template_list()
        else: # individual collectors, monitor, periodic
            return RapidDiagCLI().invoke_collector(args.mode, args.collector, args)

        return ErrorCodes.INVALID_COMMAND
    except argparse.ArgumentError as ae:
        sys.stderr.write(str(ae) + "\n")
        return ErrorCodes.INVALID_COMMAND
    except SystemExit as se:
        return ErrorCodes.INVALID_COMMAND if se.code == 2 else se.code
    except Exception as ex:
        sys.stderr.write("ERROR: Unknown exception caught: " + str(ex) + "\n")
        return 3


def main():
    result = run(sys.argv)
    if result == errno.ENOENT:
        sys.stderr.write("ERROR: File doesn't exist\n")
    elif result == errno.EEXIST:
        sys.stderr.write("ERROR: File already exists\n")
    elif result == errno.EACCES:
        sys.stderr.write("ERROR: Cannot write to the file\n")
    elif result == ErrorCodes.JSON_VALIDATION:
        sys.stderr.write("ERROR: JSON validation failed to load task details\n")
    elif result == ErrorCodes.DUPLICATE_TASK_ID:
        sys.stderr.write("ERROR: Duplicate task id\n")
    elif result == ErrorCodes.ACTION_ABORTED:
        sys.stderr.write("ERROR: Action aborted\n")
    elif result == ErrorCodes.COLLECTION_FAILED:
        sys.stderr.write("ERROR: Data collection failed\n")
    elif result == ErrorCodes.INVALID_COMMAND:
        pass
    elif result == 0:
        sys.stdout.write("\n")
    else:
        sys.stderr.write("ERROR: %s: Report this error to Splunk Support.\n" % (result))
    sys.exit(result)


if __name__ == '__main__':
    main()
