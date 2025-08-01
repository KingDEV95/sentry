import pytest

from sentry import eventstore
from sentry.event_manager import EventManager


@pytest.fixture
def make_geo_snapshot(insta_snapshot):
    def inner(data):
        mgr = EventManager(data={"user": {"id": "123", "geo": data}})
        mgr.normalize()
        evt = eventstore.backend.create_event(project_id=1, data=mgr.get_data())

        interface = evt.interfaces["user"].geo
        insta_snapshot(
            {"errors": evt.data.get("errors"), "to_json": interface and interface.to_json()}
        )

    return inner


def test_serialize_behavior(make_geo_snapshot) -> None:
    make_geo_snapshot({"country_code": "US", "city": "San Francisco", "region": "CA"})


@pytest.mark.parametrize("input", [{}, {"country_code": None}, {"city": None}, {"region": None}])
def test_null_values(make_geo_snapshot, input) -> None:
    make_geo_snapshot(input)
