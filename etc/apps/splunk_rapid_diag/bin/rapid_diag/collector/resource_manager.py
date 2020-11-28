import rapid_diag.util
import logger_manager as log
from rapid_diag.collector.trigger.trigger import Trigger

# lambda wrappers to avoid the cyclic import problem
util_mod = lambda: rapid_diag.util

_LOGGER = log.setup_logging("resource_manager")


class ResourceManager(object):
    """Collector resource manager which will act as a gatekeeper to start the collection task.
    Manager calculates the allocated and required resources, based on that it finds the conflicting resources.
    If there are no conflicting resources, user can start the collection task.
    Use `should_start_task` method prior to starting any collection task.
    As an extra precautionary measure use the aforementioned method before starting collectors from inside the triggers.

    Parameters
    ----------
    incoming_task_collectors : list
        list of collectors present in incoming task
    """
    def __init__(self, incoming_task_collectors=None):
        self.incoming_task_collectors = incoming_task_collectors
        self.conflicting_resources = set()

    def get_allocated_resources(self, running_tasks):
        """Find and return the allocated colelctor resources in the system

        Parameters
        ----------
        running_tasks : list
            list of running task objects

        Returns
        -------
        set
            resources allocated
        """
        allocated_resources = set()

        for task in running_tasks:
            if task.status == task.COLLECTING:
                for collector in util_mod().flatten_collectors(task.task.collectors):
                    if (not isinstance(collector, Trigger)) and collector.state == collector.State.COLLECTING:
                        allocated_resources.update(collector.get_required_resources())

        _LOGGER.debug("Allocated resources are " + " none." if not allocated_resources else " ".join(list(map(str, allocated_resources))))
        return allocated_resources

    def get_required_resources(self):
        """Calculate and return the resources required by the incoming collection.

        Returns
        -------
        set
            resources required
        """
        required_resources = set()

        for collector in util_mod().flatten_collectors(self.incoming_task_collectors):
            required_resources.update(collector.get_required_resources())

        _LOGGER.debug("Required_resources are " + ("none." if not required_resources else " ".join(list(map(str, required_resources)))))
        return required_resources

    def find_conflicting_resources(self, running_tasks):
        """Find those required resources that conflicts with the allocated resources.

        Parameters
        ----------
        running_tasks : list
            list of running task objects
        """
        allocated_resources = self.get_allocated_resources(running_tasks)
        required_resources = self.get_required_resources()

        self.conflicting_resources = allocated_resources.intersection(required_resources)
        _LOGGER.info("Conflicting_resources are " + ("none." if not self.conflicting_resources else " ".join(list(map(str, self.conflicting_resources)))))

    def should_start_task(self):
        """Check if task collection can be started. Allow only if there are no conflicting resources.

        Returns
        -------
        bool
            should allow the collection to run
        """
        import rapid_diag.task_handler
        task_handler_mod = lambda: rapid_diag.task_handler
        server = util_mod().SERVER_NAME
        running_tasks = task_handler_mod().TaskHandler()._get_tasks(server, 'running')
        self.find_conflicting_resources(running_tasks)
        return not self.conflicting_resources
