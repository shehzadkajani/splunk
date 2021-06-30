from spacebridgeapp.data.dashboard_data import VisualizationData, TrellisVisualizationData, TrellisCells, Column
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_process_trellis.log",
                       "process_trellis")

SPLITBY_FIELD = "splitby_field"
SPLITBY_VALUE ="splitby_value"
DATA_SOURCE = "data_source"
GROUPBY_RANK = "groupby_rank"

def process_trellis_format(visualization_data, trellis_split_by):
    """
    Formats Trellis visualization type
    :param visualization_data: data set returned from Splunk
    :param trellis_split_by: field to split data by
    :return: List of VisualizationData
    """
    fields_meta_list = visualization_data.fields_meta_list
    default_group_by = [field['name'] for field in fields_meta_list if field.get(GROUPBY_RANK) == '0'][0]
    if (not trellis_split_by) or trellis_split_by == default_group_by:
        trellis_visualization_data = process_default_group_by(visualization_data, trellis_split_by)
    else:
        trellis_visualization_data = process_non_default_group_by(visualization_data, trellis_split_by)

    return trellis_visualization_data


def process_default_group_by(visualization_data, trellis_split_by):
    field_names = visualization_data.field_names
    columns = visualization_data.columns
    fields_meta_list = visualization_data.fields_meta_list

    all_splitby_fields = {}
    all_splitby_values = {}
    all_data_sources = {}
    for index, field in enumerate(fields_meta_list):
        splitby_field = field.get(SPLITBY_FIELD)
        splitby_value = field.get(SPLITBY_VALUE)
        data_source = field.get(DATA_SOURCE)
        if splitby_field and splitby_value and data_source:
            all_splitby_fields[splitby_field] = True
            all_splitby_values[splitby_value] = True
            if all_data_sources.get(data_source):
                all_data_sources[data_source].append(index)
            else:
                all_data_sources[data_source] = [index]

    trellis_cells_names = TrellisCells(cells=columns[0].values)

    if all_splitby_fields and all_splitby_values and all_data_sources:
        if all_splitby_fields.keys():
            x_axis_name = list(all_splitby_fields.keys())[0]
        else:
            return None
        x_axis_values = list(all_splitby_values.keys())
        x_axis_meta = {'name': x_axis_name, GROUPBY_RANK: '0'}

        trellis_cells_field_names = [x_axis_name] + list(all_data_sources.keys())
        trellis_cells_fields_meta_list = [x_axis_meta]
        for d_s in all_data_sources.keys():
            trellis_cells_fields_meta_list.append({'name': d_s, DATA_SOURCE: d_s})
        trellis_cells = []
        for trellis_index, trellis_cell_name in enumerate(trellis_cells_names.cells):
            trellis_cell_columns = [Column(values=x_axis_values)]
            for data_source in all_data_sources:
                data_source_indexes = all_data_sources[data_source]
                trellis_data_source_column = [str(c.values[trellis_index]) for i, c in enumerate(columns) if i in data_source_indexes]
                trellis_cell_columns.append(Column(values=trellis_data_source_column))

            trellis_visualization_data = VisualizationData(field_names=trellis_cells_field_names,
                                                           columns=trellis_cell_columns,
                                                           fields_meta_list=trellis_cells_fields_meta_list)
            trellis_cells.append(trellis_visualization_data)

        trellis_visualization_data = TrellisVisualizationData(trellis_cells=trellis_cells_names,
                                                              visualization_data=trellis_cells)
    else:
        trellis_cells_values = columns[1].values
        trellis_cells_field_name = field_names[1]
        trellis_cells_field_meta_list = fields_meta_list[1]
        trellis_cells = []
        for trellis_index, trellis_cell_name in enumerate(trellis_cells_names.cells):
            trellis_cell_columns = Column(values=[trellis_cells_values[trellis_index]])

            trellis_visualization_data = VisualizationData(field_names=[trellis_cells_field_name],
                                                           columns=[trellis_cell_columns],
                                                           fields_meta_list=[trellis_cells_field_meta_list])
            trellis_cells.append(trellis_visualization_data)

        trellis_visualization_data = TrellisVisualizationData(trellis_cells=trellis_cells_names,
                                                              visualization_data=trellis_cells)

    return trellis_visualization_data


def process_non_default_group_by(visualization_data, trellis_split_by):
    # Object with splitby_value as the key, this is the title of the trellis cell, and the sources and their indexes
    # for that split as the value
    field_names = visualization_data.field_names
    columns = visualization_data.columns
    fields_meta_list = visualization_data.fields_meta_list
    source_splits = {}
    for index, field in enumerate(fields_meta_list):
        splitby_field = field.get(SPLITBY_FIELD)
        splitby_value = field.get(SPLITBY_VALUE)
        data_source = field.get(DATA_SOURCE)
        if splitby_field == trellis_split_by:
            if source_splits.get(splitby_value):
                source_splits[splitby_value].append(index)
            else:
                source_splits[splitby_value] = [index]

    x_axis_name = field_names[0]
    x_axis_values = columns[0].values
    x_axis_meta = fields_meta_list[0]

    trellis_cells = []

    for split_name in source_splits.keys():
        indexes = [0] + source_splits[split_name]
        trellis_cell_field_names = [f for i, f in enumerate(field_names) if i in indexes]
        trellis_cell_columns = [c for i, c in enumerate(columns) if i in indexes]
        trellis_cell_fields_meta_list = [f_m for i, f_m in enumerate(fields_meta_list) if i in indexes]
        trellis_visualization_data = VisualizationData(field_names=trellis_cell_field_names,
                                                       columns=trellis_cell_columns,
                                                       fields_meta_list=trellis_cell_fields_meta_list)
        trellis_cells.append(trellis_visualization_data)

    trellis_cells_names = TrellisCells(cells=list(source_splits.keys()))
    trellis_visualization_data = TrellisVisualizationData(trellis_cells=trellis_cells_names, visualization_data=trellis_cells)
    return trellis_visualization_data
