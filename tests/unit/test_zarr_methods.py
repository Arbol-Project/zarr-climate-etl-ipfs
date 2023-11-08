import os
import json

import pandas as pd
import numpy as np
import xarray as xr

from gridded_etl_tools.dataset_manager import DatasetManager
from ..common import get_manager, patched_irregular_update_cadence


def test_standard_dims(mocker, manager_class: DatasetManager):
    """
    Test that standard dimensions are correctly instantiated for regular, forecast, and ensemble datasets
    """
    dm = get_manager(manager_class)
    # Test normal standard dims
    dm.set_key_dims()
    assert dm.standard_dims == ["time", "latitude", "longitude"]
    assert dm.time_dim == "time"
    # Forecast standard dims
    mocker.patch("gridded_etl_tools.utils.attributes.Attributes.forecast", return_value=True)
    dm.set_key_dims()
    assert dm.standard_dims == [
        "forecast_reference_time",
        "step",
        "latitude",
        "longitude",
    ]
    assert dm.time_dim == "forecast_reference_time"
    # Ensemble standard dims
    mocker.patch("gridded_etl_tools.utils.attributes.Attributes.ensemble", return_value=True)
    dm.set_key_dims()
    assert dm.standard_dims == [
        "forecast_reference_time",
        "step",
        "ensemble",
        "latitude",
        "longitude",
    ]
    assert dm.time_dim == "forecast_reference_time"
    # Ensemble standard dims
    mocker.patch("gridded_etl_tools.utils.attributes.Attributes.hindcast", return_value=True)
    dm.set_key_dims()
    assert dm.standard_dims == [
        "hindcast_reference_time",
        "forecast_reference_offset",
        "step",
        "ensemble",
        "latitude",
        "longitude",
    ]
    assert dm.time_dim == "hindcast_reference_time"


def test_export_zarr_json_in_memory(manager_class: DatasetManager, example_zarr_json):
    dm = get_manager(manager_class)
    local_file_path = "output_zarr_json.json"
    json_str = str(example_zarr_json)
    dm.zarr_json_in_memory_to_file(json_str, local_file_path=local_file_path)
    assert os.path.exists(local_file_path)
    os.remove(local_file_path)


def test_preprocess_kerchunk(mocker, manager_class: DatasetManager, example_zarr_json: dict):
    """
    Test that the preprocess_kerchunk method successfully changes the _FillValue attribute of all arrays
    """
    orig_fill_value = json.loads(example_zarr_json["refs"]["latitude/.zarray"])["fill_value"]
    # prepare a dataset manager and preprocess a Zarr JSON
    dm = get_manager(manager_class)
    mocker.patch(
        "tests.unit.conftest.DummyManager.missing_value_indicator",
        return_value=-8888,
    )
    pp_zarr_json = dm.preprocess_kerchunk(example_zarr_json["refs"])
    # populate before/after fill value variables
    modified_fill_value = int(json.loads(pp_zarr_json["latitude/.zarray"])["fill_value"])
    # test that None != -8888
    assert orig_fill_value != modified_fill_value
    assert modified_fill_value == -8888


def test_are_times_in_expected_order(mocker, manager_class: DatasetManager):
    """
    Test that the check for non-contiguous times successfully catches bad times
    while letting anticipated irregular times pass
    """
    # prepare a dataset manager
    dm = get_manager(manager_class)
    # Check a set of contiguous times
    contig = pd.date_range(start="2023-03-01", end="2023-03-15", freq="1D")
    expected_delta = contig[1] - contig[0]
    assert dm.are_times_in_expected_order(contig, expected_delta=expected_delta)
    # Check a single time -- one good, one not
    check1 = [contig[0], contig[1]]
    check2 = [contig[0], contig[2]]
    assert dm.are_times_in_expected_order(check1, expected_delta=expected_delta)
    assert not dm.are_times_in_expected_order(check2, expected_delta=expected_delta)
    # Check a set of times that skips a day
    week_ahead_dt = contig[-1] + pd.Timedelta(days=7)
    week_gap = contig.union([week_ahead_dt])
    assert not dm.are_times_in_expected_order(week_gap, expected_delta=expected_delta)
    # Check a set of times that's out of order
    week_behind_dt = contig[0] - pd.Timedelta(days=7)
    week_gap = contig.union([week_behind_dt])
    assert not dm.are_times_in_expected_order(week_gap, expected_delta=expected_delta)
    # Check a set of times that's badly out of order
    out_of_order = [contig[1], contig[2], contig[0], contig[12], contig[3]]
    assert not dm.are_times_in_expected_order(out_of_order, expected_delta=expected_delta)
    # Check that irregular cadences pass
    mocker.patch(
        "gridded_etl_tools.utils.attributes.Attributes.irregular_update_cadence", patched_irregular_update_cadence
    )
    three_and_four_day_updates = [contig[0], contig[3], contig[6], contig[10]]
    assert dm.are_times_in_expected_order(three_and_four_day_updates, expected_delta=expected_delta)
    # Check that ranges outside the irregular cadence still fail
    five_day_updates = [contig[0], contig[3], contig[6], contig[11], contig[14]]
    assert not dm.are_times_in_expected_order(five_day_updates, expected_delta=expected_delta)


def test_calculate_update_time_ranges(
    manager_class: DatasetManager,
    fake_original_dataset: xr.Dataset,
    fake_complex_update_dataset: xr.Dataset,
):
    """
    Test that the calculate_date_ranges function correctly prepares insert and append date ranges as anticipated
    """
    # prepare a dataset manager
    dm = get_manager(manager_class)
    dm.set_key_dims()
    datetime_ranges, regions_indices = dm.calculate_update_time_ranges(
        fake_original_dataset, fake_complex_update_dataset
    )
    # Test that 7 distinct updates -- 6 inserts and 1 append -- have been prepared
    assert len(regions_indices) == 7
    # Test that all of the updates are of the expected sizes
    insert_range_sizes = []
    for region in regions_indices:
        index_range = region[1] - region[0]
        insert_range_sizes.append(index_range)
    assert insert_range_sizes == [1, 8, 1, 1, 12, 1, 1]
    # Test that the append is of the expected size
    append_update = datetime_ranges[-1]
    append_size = (append_update[-1] - append_update[0]).astype("timedelta64[D]")
    assert append_size == np.timedelta64(35, "D")