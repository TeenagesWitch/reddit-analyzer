import datetime

import pytest

from reddit_analyzer.core.timestamps import parse_timestamp_utc

UTC = datetime.timezone.utc
EXPECTED = datetime.datetime(2015, 1, 1, 2, 0, tzinfo=UTC)


@pytest.mark.parametrize('value', [1420077600, 1420077600.0, '1420077600', ' 1420077600 ',
                                   '2015-01-01T02:00:00', '2015-01-01T02:00:00Z',
                                   '2015-01-01T04:00:00+02:00'])
def test_parses_epochs_and_iso_strings_to_utc(value):
    assert parse_timestamp_utc(value) == EXPECTED


@pytest.mark.parametrize('value', [None, True, False, '', 'garbage', [], {}, float('inf')])
def test_unparseable_values_give_none(value):
    assert parse_timestamp_utc(value) is None


def test_result_does_not_depend_on_local_timezone():
    # Just after midnight UTC: a local-time conversion west of UTC would land on the previous day
    assert parse_timestamp_utc(1420070460).date() == datetime.date(2015, 1, 1)
