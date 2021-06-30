"""
Copyright (C) 2009-2020 Splunk Inc. All Rights Reserved.

Hosts APIs for listing one or more JSON formatted DashboardDescriptions.
"""
import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_secure_gateway', 'bin']))
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_secure_gateway', 'lib']))
from spacebridgeapp.util import py23

from http import HTTPStatus
from spacebridgeapp.util.constants import PAYLOAD, STATUS
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.rest.async_bridge.async_bridge_requests import dashboard_list_request


class DashboardsHandler(async_base_endpoint.AsyncBaseRestHandler):

    async def get(self, request):
        """
        Lists one or more dashboards in the form of JSON formatted DashboardDescription messages.

        Request Parameters
            offset         the number of dashboards to skip
            max_results    the maximum number of dashboards to return
            dashboard_ids  one or more dashboard IDs to query
            minimal_list   0 for verbose descriptions and 1 for minimal descriptions
        """
        context = RequestContext.from_rest_request(request)
        response = await dashboard_list_request(request, self.async_client_factory, context)
        return {
            PAYLOAD: response,
            STATUS: HTTPStatus.INTERNAL_SERVER_ERROR if 'error' in response else HTTPStatus.OK,
        }
