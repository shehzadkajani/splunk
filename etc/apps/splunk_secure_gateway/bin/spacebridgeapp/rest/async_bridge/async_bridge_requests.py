"""
Copyright (C) 2009-2020 Splunk Inc. All Rights Reserved.

Module containing functions called by the async bridge rest handler
"""
from google.protobuf.json_format import MessageToDict
from splapp_protocol import request_pb2
from spacebridgeapp.request.dashboard_request_processor import process_dashboard_list_request
from spacebridgeapp.util.constants import QUERY, DASHBOARD_IDS, MINIMAL_LIST, MAX_RESULTS, OFFSET


async def dashboard_list_request(request, async_client_factory, request_context):
    """
    REST handler to fetch a list of dashboards
    """

    try:
        offset = request[QUERY].get(OFFSET)
        max_results = request[QUERY].get(MAX_RESULTS)
        dashboard_ids = request[QUERY].get(DASHBOARD_IDS)
        minimal_list = int(request[QUERY].get(MINIMAL_LIST, 0))

        client_request_proto = request_pb2.ClientSingleRequest()
        dashboard_request = client_request_proto.dashboardListRequest
        if dashboard_ids:
            dashboard_ids = [dashboard_ids] if not isinstance(dashboard_ids, list) else dashboard_ids
            dashboard_request.dashboardIds.extend(dashboard_ids)
        if offset:
            dashboard_request.offset = int(offset)
        if max_results:
            dashboard_request.maxResults = int(max_results)
        dashboard_request.minimalList = minimal_list

        server_response_proto = request_pb2.ServerSingleResponse()

        await process_dashboard_list_request(request_context,
                                             client_request_proto,
                                             server_response_proto,
                                             async_client_factory)

        return MessageToDict(server_response_proto)
    except Exception as e:
        return {'error': str(e)}
