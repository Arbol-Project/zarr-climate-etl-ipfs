import pytest

import numpy as np
import xarray as xr

from gridded_etl_tools.dataset_manager import DatasetManager
from ..common import get_manager, remove_mock_output


@pytest.fixture(scope="function")
def setup_and_teardown():
    """
    Call the setup functions first, in a chain ending with `simulate_file_download`.
    Next run the test in question. Finally, remove generated inputs afterwards, even if the test fails.
    """
    yield  # run the tests first
    # delete temp files
    remove_mock_output()


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


def test_post_parse_attrs(manager_class: DatasetManager, fake_original_dataset: xr.Dataset):
    dm = manager_class()
    dm.update_attributes = ["date range", "update_previous_end_date", "another attribute"]
    post_update_dict = {
        "date range": ["2000010100", "2021010523"],
        "update_previous_end_date": "2020123123",
        "another attribute": True,
        "update_in_progress": False,
        "initial_parse" : False
    }
    # Mock datasets
    dataset = fake_original_dataset
    dataset.attrs.update(**post_update_dict)
    assert dm.move_post_parse_attrs_to_dict(dataset)[1] == post_update_dict
