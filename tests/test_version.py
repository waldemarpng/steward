from importlib.metadata import version

import steward
from steward_client import __version__ as client_version


def test_package_versions_match() -> None:
    assert steward.__version__ == version("steward")
    assert client_version == version("steward-client")
    assert steward.__version__ == client_version
