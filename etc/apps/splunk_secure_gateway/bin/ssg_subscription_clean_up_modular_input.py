"""
Copyright (C) 2009-2020 Splunk Inc. All Rights Reserved.

Modular Input for deleting expired subscriptions
"""

import warnings
warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)

import sys
import os
from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from solnlib import modular_input
from spacebridgeapp.util.splunk_utils.common import modular_input_should_run
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.subscriptions.subscription_clean_up import SubscriptionCleanUp


class SubscriptionCleanUpModularInput(modular_input.ModularInput):
    title = 'Splunk Secure Gateway Subscription Clean Up'
    description = 'Clean up expired subscriptions'
    app = 'Splunk Secure Gateway'
    name = 'splunk_secure_gateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(SPACEBRIDGE_APP_NAME + '.log', 'ssg_subscription_clean_up_modular_input.app')
    input_config_key = "ssg_subscription_clean_up_modular_input://default"
    config_key_cleanup_threshold_seconds = "cleanup_threshold_seconds"

    def do_run(self, input_config):
        """
        Executes the modular input
        :param input_config:
        :return:
        """
        if not modular_input_should_run(self.session_key, logger=self.logger):
            self.logger.debug("Modular input will not run on this node.")
            return

        self.logger.debug("Running Subscription Clean Up modular input on search captain node")
        cleanup_time_seconds = input_config[self.input_config_key][self.config_key_cleanup_threshold_seconds]
        subscription_clean_up = SubscriptionCleanUp(self.session_key, int(cleanup_time_seconds))

        try:
            subscription_clean_up.run()
        except:
            self.logger.exception("Failure encountered while running Subscription Clean Up")


if __name__ == "__main__":
    worker = SubscriptionCleanUpModularInput()
    worker.execute()
