"""
Copyright (C) 2009-2020 Splunk Inc. All Rights Reserved.

Modular input for the Spacebridge app which brings up
a web socket server to talk to Spacebridge
"""

import warnings

warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)

import sys
import os
import time
from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from solnlib import modular_input
from spacebridgeapp.util.splunk_utils.common import modular_input_should_run
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.metrics.metrics_collector import SpacebridgeaAppMetricsCollector


class MetricsModularInput(modular_input.ModularInput):
    """

    Modular input to periodically collect secure gateway metrics
    """
    title = 'Splunk Secure Gateway Metrics Collector'
    description = 'Collects metrics for Splunk Secure Gateway'
    app = 'Splunk Secure Gateway'
    name = 'splunk_secure_gateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_metrics.log', 'secure_gateway_metrics.app')
    input_config_key = "ssg_metrics_modular_input://default"

    def do_run(self, input_config):
        """
        Main entry path for input
        """
        self.logger.info("Running secure gateway metrics modular input")
        if not modular_input_should_run(self.session_key, logger=self.logger):
            self.logger.debug("Modular input will not run on this node.")
            return

        try:
            time.sleep(30)
            collector = SpacebridgeaAppMetricsCollector(self.logger, self.session_key)
            collector.run()
        except:
            self.logger.exception("Exception calculating secure gateway metrics")


if __name__ == "__main__":
    worker = MetricsModularInput()
    worker.execute()
