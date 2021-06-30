"""
Copyright (C) 2009-2020 Splunk Inc. All Rights Reserved.

Module for any requests that will return the raw json
"""
from http import HTTPStatus
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.logging.spacebridge_logging import setup_logging
from spacebridgeapp.dashboard.dashboard_helpers import generate_search_str
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_dashboard_request_json.log", "dashboard_request_json")


async def fetch_dashboard_list_json(request_context,
                                    offset=0,
                                    max_results=0,
                                    app_names=[],
                                    dashboard_ids=[],
                                    async_splunk_client=None):
    """
    Fetch the dashboard list json Splunk api /data/ui/views
    :param request_context:
    :param offset:
    :param max_results:
    :param app_names:
    :param dashboard_ids:
    :param async_splunk_client:
    :return:
    """
    search_str = generate_search_str(app_names, dashboard_ids)
    params = {'output_mode': 'json',
              'search': search_str,
              'sort_dir': 'asc',
              'sort_key': 'label',
              'sort_mode': 'alpha',
              'offset': offset,
              'count': max_results}

    # Don't specify owner, defaults to '-' which will retrieve dashboards from all users visible for current_user
    response = await async_splunk_client.async_get_dashboard_list_request(auth_header=request_context.auth_header,
                                                                          params=params)

    LOGGER.info(f'fetch_dashboard_list_json response={response.code}')

    if response.code != HTTPStatus.OK:
        response_text = await response.text()
        raise SpacebridgeApiRequestError(f"Failed fetch_dashboard_list_json "
                                         f"response.code={response.code}, response.text={response_text}",
                                         status_code=response.code)

    response_json = await response.json()
    return response_json

