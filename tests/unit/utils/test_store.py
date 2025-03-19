import datetime
import json
import os
import pathlib
from unittest import mock

import pytest

from gridded_etl_tools.utils import store as store_module


class DummyStoreImpl(store_module.StoreInterface):
    has_existing = True

    def __init__(self, dm):
        super().__init__(dm)
        self._mapper = mock.Mock()
        self._path = mock.Mock(return_value="winding")

    def get_metadata_path(self, title: str, stac_type: str):  # pragma NO COVER
        raise NotImplementedError

    def metadata_exists(self, title: str, stac_type: str):  # pragma NO COVER
        raise NotImplementedError

    def push_metadata(self, title: str, stac_content: dict, stac_type: str):  # pragma NO COVER
        raise NotImplementedError

    def retrieve_metadata(self, title: str, stac_type: str):  # pragma NO COVER
        raise NotImplementedError

    def write_metadata_only(self, attributes: dict):  # pragma NO COVER
        raise NotImplementedError

    def mapper(self, **kwargs):
        return self._mapper(**kwargs)

    @property
    def path(self):
        return self._path()


class TestStoreInterface:
    @staticmethod
    def test_constructor():
        dm = object()
        store = DummyStoreImpl(dm)

        assert store.dm is dm

    @staticmethod
    def test_dataset(mocker):
        xr = mocker.patch("gridded_etl_tools.utils.store.xr")
        dataset = xr.open_zarr.return_value

        store = DummyStoreImpl(None)
        assert store.dataset(arbitrary="keyword") is dataset

        xr.open_zarr.assert_called_once_with(store=store.path, consolidated=False, arbitrary="keyword")

    @staticmethod
    def test_dataset_not_existing(mocker):
        xr = mocker.patch("gridded_etl_tools.utils.store.xr")

        store = DummyStoreImpl(None)
        store.has_existing = False
        assert store.dataset() is None

        xr.open_zarr.assert_not_called()
        store._mapper.assert_not_called()


class TestS3:
    @staticmethod
    def test_constructor():
        dm = object()
        bucket = "drops"

        store = store_module.S3(dm, bucket)

        assert store.dm is dm
        assert store.bucket == bucket

    @staticmethod
    def test_constructor_no_bucket():
        dm = object()

        with pytest.raises(ValueError):
            store_module.S3(dm, "")

    @staticmethod
    def test_fs(mocker):
        s3fs = mocker.patch("gridded_etl_tools.utils.store.s3fs")
        store = store_module.S3(mock.Mock(), "bucket")
        fs = s3fs.S3FileSystem.return_value

        assert store.fs() is fs
        assert store.fs() is fs  # second call returns cached value

        s3fs.S3FileSystem.assert_called_once_with(profile=None)

    @staticmethod
    def test_fs_refresh(mocker):
        s3fs = mocker.patch("gridded_etl_tools.utils.store.s3fs")
        store = store_module.S3(mock.Mock(), "bucket")
        store._fs = object()
        fs = s3fs.S3FileSystem.return_value

        assert store.fs(refresh=True) is fs

        s3fs.S3FileSystem.assert_called_once_with(profile=None)

    @staticmethod
    def test_fs_refresh_profile(mocker):
        s3fs = mocker.patch("gridded_etl_tools.utils.store.s3fs")
        store = store_module.S3(mock.Mock(), "bucket")
        store._fs = object()
        fs = s3fs.S3FileSystem.return_value

        assert store.fs(refresh=True, profile="slim") is fs

        s3fs.S3FileSystem.assert_called_once_with(profile="slim")

    @staticmethod
    def test_path():
        dm = mock.Mock(key=mock.Mock(return_value="hello_mother"), custom_output_path=None)
        store = store_module.S3(dm, "mop_bucket")
        assert store.path == "s3://mop_bucket/datasets/hello_mother.zarr"

    @staticmethod
    def test_path_customized():
        dm = mock.Mock(key=mock.Mock(return_value="hello_mother"), custom_output_path="use/this/one/instead.zarr")
        store = store_module.S3(dm, "mop_bucket")
        assert store.path == "use/this/one/instead.zarr"

    @staticmethod
    def test___repr__():
        dm = mock.Mock(custom_output_path=mock.MagicMock())
        store = store_module.S3(dm, "mop_bucket")
        assert str(store) == "S3"

    @staticmethod
    def test_mapper(mocker):
        s3fs = mocker.patch("gridded_etl_tools.utils.store.s3fs")
        mapper = s3fs.S3Map.return_value
        store = store_module.S3(mock.Mock(custom_output_path="put/it/here.zarr"), "bucket")
        store.fs = mock.Mock()

        fs = store.fs.return_value

        assert store.mapper(arbitrary="keyword") is mapper
        assert store.mapper() is mapper  # second call uses cached object

        store.fs.assert_called_once_with()
        s3fs.S3Map.assert_called_once_with(root="put/it/here.zarr", s3=fs)

    @staticmethod
    def test_mapper_refresh(mocker):
        s3fs = mocker.patch("gridded_etl_tools.utils.store.s3fs")
        mapper = s3fs.S3Map.return_value
        store = store_module.S3(mock.Mock(custom_output_path="put/it/here.zarr"), "bucket")
        store.fs = mock.Mock()
        store._mapper = object()

        fs = store.fs.return_value

        assert store.mapper(refresh=True) is mapper

        store.fs.assert_called_once_with()
        s3fs.S3Map.assert_called_once_with(root="put/it/here.zarr", s3=fs)

    @staticmethod
    def test_has_existing():
        store = store_module.S3(mock.Mock(custom_output_path="it/is/here.zarr"), "bucket")
        store.fs = mock.Mock()
        fs = store.fs.return_value

        assert store.has_existing is fs.exists.return_value

        store.fs.assert_called_once_with()
        fs.exists.assert_called_once_with("it/is/here.zarr")

    @staticmethod
    def test_push_metadata_path_does_not_exist():
        store = store_module.S3(None, "mopwater")
        store.get_metadata_path = mock.Mock(return_value="path/to/meta/data")
        store.fs = mock.Mock()
        fs = store.fs.return_value
        fs.exists.return_value = False

        store.push_metadata("War and Peace", {"meta": "data"}, "fiction")

        store.fs.assert_called_once_with()
        store.get_metadata_path.assert_called_once_with("War and Peace", "fiction")
        fs.exists.assert_called_once_with("path/to/meta/data")
        fs.ls.assert_not_called()
        fs.copy.assert_not_called()
        fs.write_text.assert_called_once_with("path/to/meta/data", '{"meta": "data"}')

    @staticmethod
    def test_push_metadata_path_exists():
        store = store_module.S3(None, "mopwater")
        store.get_metadata_path = mock.Mock(return_value="path/to/meta/data")
        store.fs = mock.Mock()
        fs = store.fs.return_value
        fs.exists.return_value = True
        fs.ls.return_value = [
            {"LastModified": datetime.datetime(1975, 12, 25, 6, 0, 0)},
            "NobodyCares",
        ]

        store.push_metadata("War and Peace", {"meta": "data"}, "fiction")

        store.fs.assert_called_once_with()
        store.get_metadata_path.assert_called_once_with("War and Peace", "fiction")
        fs.exists.assert_called_once_with("path/to/meta/data")
        fs.ls.assert_called_once_with("path/to/meta/data", detail=True)
        fs.copy.assert_called_once_with(
            "path/to/meta/data", "s3://mopwater/history/War and Peace/War and Peace-1975-12-25T06:00:00.json"
        )
        fs.write_text.assert_called_once_with("path/to/meta/data", '{"meta": "data"}')

    @staticmethod
    def test_retrieve_metadata():
        store = store_module.S3(None, "bucket")
        store.get_metadata_path = mock.Mock(return_value="meta/data/goes/here")
        store.fs = mock.Mock()
        fs = store.fs.return_value
        fs.cat.return_value = '{"meta": {"meta": "data"}}'

        assert store.retrieve_metadata("Tom Sawyer", "book not song") == (
            {"meta": {"meta": "data"}},
            "meta/data/goes/here",
        )

        store.get_metadata_path.assert_called_once_with("Tom Sawyer", "book not song")
        store.fs.assert_called_once_with()
        fs.cat.assert_called_once_with("meta/data/goes/here")

    @staticmethod
    def test_metadata_exists():
        store = store_module.S3(None, "bucket")
        store.get_metadata_path = mock.Mock(return_value="meta/data/here")
        store.fs = mock.Mock()
        fs = store.fs.return_value

        assert store.metadata_exists("Marquee Moon", "The Album") is fs.exists.return_value

        store.fs.assert_called_once_with()
        store.get_metadata_path.assert_called_once_with("Marquee Moon", "The Album")
        fs.exists.assert_called_once_with("meta/data/here")

    @staticmethod
    def test_get_metadata_path():
        store = store_module.S3(None, "sop")
        assert store.get_metadata_path("Die Hard", "film") == "s3://sop/metadata/film/Die Hard.json"
        assert store.get_metadata_path("Hammer of the Bobs", "") == "s3://sop/metadata/Hammer of the Bobs.json"

    @staticmethod
    def test_write_metadata_only(tmpdir):
        with open(tmpdir / "zarr.json", "w") as f:
            json.dump({"attributes": {"meta": "data"}}, f)

        store = store_module.S3(mock.Mock(custom_output_path=tmpdir), "bucket")
        store.fs = mock.Mock()
        fs = store.fs.return_value
        fs.open = open

        store.write_metadata_only({"new": "value"})

        store.fs.assert_called_once_with()

        with open(tmpdir / "zarr.json") as f:
            assert json.load(f) == {"attributes": {"meta": "data", "new": "value"}}


class TestLocal:
    @staticmethod
    def test_fs(mocker):
        fsspec = mocker.patch("gridded_etl_tools.utils.store.fsspec")
        store = store_module.Local(mock.Mock())
        fs = fsspec.filesystem.return_value

        assert store.fs() is fs
        assert store.fs() is fs  # second call returns cached value

        fsspec.filesystem.assert_called_once_with("file")

    @staticmethod
    def test_fs_refresh(mocker):
        fsspec = mocker.patch("gridded_etl_tools.utils.store.fsspec")
        store = store_module.Local(mock.Mock())
        store._fs = object()
        fs = fsspec.filesystem.return_value

        assert store.fs(refresh=True) is fs

        fsspec.filesystem.assert_called_once_with("file")

    @staticmethod
    def test_mapper():
        store = store_module.Local(mock.Mock(custom_output_path="el/cami/no"))
        store.fs = mock.Mock()
        fs = store.fs.return_value
        mapper = fs.get_mapper.return_value

        assert store.mapper(arbitrary="keyword") is mapper
        assert store.mapper() is mapper  # Second call returns cached copy

        store.fs.assert_called_once_with()
        fs.get_mapper.assert_called_once_with("el/cami/no")

    @staticmethod
    def test_mapper_refresh():
        store = store_module.Local(mock.Mock(custom_output_path="el/cami/no"))
        store.fs = mock.Mock()
        fs = store.fs.return_value
        mapper = fs.get_mapper.return_value
        store._mapper = object()

        assert store.mapper(refresh=True) is mapper

        store.fs.assert_called_once_with()
        fs.get_mapper.assert_called_once_with("el/cami/no")

    @staticmethod
    def test___repr__():
        dm = mock.Mock(custom_output_path=mock.MagicMock())
        store = store_module.Local(dm)
        assert str(store) == "Local"

    @staticmethod
    def test_path():
        dm = mock.Mock(
            output_path=mock.Mock(return_value=pathlib.PosixPath("hi/mom")),
            custom_output_path=None,
            dataset_name="Jeremy",
        )
        store = store_module.Local(dm)
        assert store.path == pathlib.PosixPath("hi/mom/Jeremy.zarr")

        dm.output_path.assert_called_once_with()

    @staticmethod
    def test_path_custom():
        dm = mock.Mock(
            output_path=mock.Mock(return_value=pathlib.PosixPath("hi/mom")),
            custom_output_path="hello/dad/iminjail.zarr",
        )
        dm.name = mock.Mock(return_value="Jeremy")
        store = store_module.Local(dm)
        assert store.path == "hello/dad/iminjail.zarr"

        dm.output_path.assert_not_called()
        dm.name.assert_not_called()

    @staticmethod
    def test_has_existing():
        store = store_module.Local(mock.Mock())
        path = store.dm.custom_output_path

        assert store.has_existing is path.exists.return_value

        path.exists.assert_called_once_with()

    @staticmethod
    def test_push_metadata(tmpdir):
        metadata_path = tmpdir / "ztest.json"
        store = store_module.Local(mock.Mock())
        store.get_metadata_path = mock.Mock(return_value=metadata_path)
        store.push_metadata("Jacky", {"meta": "data"}, "song")

        with open(metadata_path) as f:
            assert json.load(f) == {"meta": "data"}

        store.get_metadata_path.assert_called_once_with("Jacky", "song")

    @staticmethod
    def test_push_metadata_overwrite(tmpdir):
        metadata_path = tmpdir / "ztest.json"
        with open(metadata_path, "w") as f:
            json.dump({"prev": "data"}, f)
        os.utime(metadata_path, (1692639017, 1692639017))  # 2023-08-21T13:30:17

        store = store_module.Local(mock.Mock(), tmpdir)
        store.get_metadata_path = mock.Mock(return_value=metadata_path)

        store.push_metadata("Jacky", {"meta": "data"}, "song")

        with open(metadata_path) as f:
            assert json.load(f) == {"meta": "data"}

        with open(tmpdir / "history" / "Jacky" / "Jacky-2023-08-21T17:30:17.json") as f:
            assert json.load(f) == {"prev": "data"}

        store.get_metadata_path.assert_called_once_with("Jacky", "song")

    @staticmethod
    def test_retrieve_metadata(tmpdir):
        metadata_path = tmpdir / "ztest.json"
        with open(metadata_path, "w") as f:
            json.dump({"meta": "data"}, f)

        store = store_module.Local(mock.Mock())
        store.get_metadata_path = mock.Mock(return_value=metadata_path)

        assert store.retrieve_metadata("Jacky", "song") == ({"meta": "data"}, metadata_path)
        store.get_metadata_path.assert_called_once_with("Jacky", "song")

    @staticmethod
    def test_metadata_exists_false(tmpdir):
        metadata_path = tmpdir / "ztest.json"

        store = store_module.Local(mock.Mock())
        store.get_metadata_path = mock.Mock(return_value=metadata_path)

        assert store.metadata_exists("Jacky", "song") is False
        store.get_metadata_path.assert_called_once_with("Jacky", "song")

    @staticmethod
    def test_get_metadata_path():
        store = store_module.Local(None, "/hi/mom")
        assert store.get_metadata_path("A Separate Peace", "novel") == "/hi/mom/metadata/novel/A Separate Peace.json"

    @staticmethod
    def test_write_metadata_only(tmpdir):
        with open(tmpdir / "zarr.json", "w") as f:
            json.dump({"attributes": {"meta": "data"}}, f)

        store = store_module.Local(mock.Mock(custom_output_path=tmpdir))
        store.write_metadata_only({"new": "value"})

        with open(tmpdir / "zarr.json") as f:
            assert json.load(f) == {"attributes": {"meta": "data", "new": "value"}}
