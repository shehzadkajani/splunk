"""Copyright (C) 2009-2020 Splunk Inc. All Rights Reserved."""
from spacebridgeapp.dashboard.dashboard_helpers import generate_visualization_id
from spacebridgeapp.dashboard.parse_helpers import get_text, get_int, to_token_list
from spacebridgeapp.data.dashboard_data import Search
from splapp_protocol import common_pb2


def string_to_refresh_type(refresh_type_string):
    """
    Helper method to return refresh_type enum from string value
    :param refresh_type_string:
    :return:
    """
    if refresh_type_string == 'delay':
        return common_pb2.DashboardVisualization.Search.REFRESH_TYPE_DELAY
    elif refresh_type_string == 'internal':
        return common_pb2.DashboardVisualization.Search.REFRESH_TYPE_INTERVAL
    return common_pb2.DashboardVisualization.Search.REFRESH_TYPE_UNKNOWN


def dashboard_query_to_spl(query):
    """
    This function will convert a dashboard xml query to spl.
    The following substitutions are made:
    1. Double dollar sign in dashboard xml is used to escape a single $
    :param query:
    :return: spl query string
    """
    # Substitute double dollar sign
    if query:
        return query.replace('$$', '$')
    return query


def build_dashboard_visualization_search(search_element=None, row_index=0, panel_index=0, dashboard_refresh=None,
                                         show_refresh=True):
    """
    Parse a <search> element into Search object
    :param search_element:
    :param row_index:
    :param panel_index:
    :param dashboard_refresh:
    :param show_refresh: show refresh params, default True
    :return:
    """
    # Return Query Value
    query = ''
    earliest = ''
    latest = ''
    search = None

    if search_element is not None:
        earliest = get_text(search_element.find('earliest'))
        latest = get_text(search_element.find('latest'))
        sample_ratio = get_int(search_element.find('sampleRatio'), 0)
        post_search = get_text(search_element.find('postSearch'))
        query = dashboard_query_to_spl(get_text(search_element.find('query')))
        ref = search_element.attrib.get('ref', '')
        base = search_element.attrib.get('base', '')
        id = search_element.attrib.get('id', '')
        depends = to_token_list(search_element.attrib.get('depends', ''))
        rejects = to_token_list(search_element.attrib.get('rejects', ''))

        # Only store values if show_refresh
        if show_refresh:
            if dashboard_refresh:
                refresh = dashboard_refresh
                refresh_type = common_pb2.DashboardVisualization.Search.REFRESH_TYPE_DELAY
            else:
                refresh = get_text(search_element.find('refresh'))
                refresh_type = string_to_refresh_type(get_text(search_element.find('refreshType')))
        else:
            refresh = ''
            refresh_type = common_pb2.DashboardVisualization.Search.REFRESH_TYPE_UNKNOWN

        # Populate Search object
        search = Search(earliest=earliest,
                        latest=latest,
                        refresh=refresh,
                        refresh_type=refresh_type,
                        sample_ratio=sample_ratio,
                        post_search=post_search,
                        query=query,
                        ref=ref,
                        base=base,
                        id=id,
                        depends=depends,
                        rejects=rejects)

    return generate_visualization_id(earliest=earliest, latest=latest, query=query, refresh=refresh,
                                     refresh_type=refresh_type, sample_ratio=sample_ratio,
                                     row_index=row_index, panel_index=panel_index, ref=ref), search
