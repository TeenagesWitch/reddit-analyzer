import datetime
import json
import os

from reddit_analyzer.config import STATUS_CODES as S
from reddit_analyzer.core import cache

TODAY = datetime.date.today().isoformat()
LONG_AGO = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()


def test_reddit_answers_are_always_reusable():
    for entry in ({'status_code': S['deleted']}, {'status_code': S['suspended']},
                  {'status_code': S['active'], 'source': 'True'}):
        assert cache.is_reusable_entry(entry)
        assert cache.is_reusable_entry(entry, oauth_available=True)


def test_unknown_entries_expire_and_are_retried_once_logged_in():
    fresh = {'status_code': S['unknown'], 'source': 'Estimated', 'checked_at': TODAY}
    stale = dict(fresh, checked_at=LONG_AGO)
    assert cache.is_reusable_entry(fresh)
    assert not cache.is_reusable_entry(stale)
    assert not cache.is_reusable_entry({'status_code': S['unknown']})       # no checked_at
    assert not cache.is_reusable_entry(fresh, oauth_available=True)        # not checked with OAuth
    assert cache.is_reusable_entry(dict(fresh, checked_with_oauth=True), oauth_available=True)
    assert not cache.is_reusable_entry(None)


def test_legacy_active_without_reddit_date_becomes_unknown():
    entries = {
        'guess': {'status_code': S['active'], 'source': 'Estimated'},
        'real': {'status_code': S['active'], 'source': 'True'},
        'gone': {'status_code': S['deleted'], 'source': 'Estimated'},
    }
    cache._migrate_legacy_entries(entries)
    assert entries['guess'] == {'status_code': S['unknown'], 'source': 'Estimated', 'checked_at': TODAY}
    assert entries['real'] == {'status_code': S['active'], 'source': 'True'}
    assert entries['gone']['status_code'] == S['deleted']


def test_save_is_atomic_and_round_trips(tmp_path):
    path = str(tmp_path / 'cache.json')
    cache.save_persistent_cache({'u': {'status_code': 1}}, path)
    assert cache.load_persistent_cache(path) == {'u': {'status_code': 1}}
    assert not os.path.exists(path + '.tmp')


def test_corrupt_cache_file_loads_as_empty(tmp_path):
    path = tmp_path / 'cache.json'
    path.write_text('{not json')
    assert cache.load_persistent_cache(str(path)) == {}


def test_flush_writes_pending_entries(tmp_path, monkeypatch):
    path = str(tmp_path / 'cache.json')
    monkeypatch.setattr(cache, 'CACHE_FILE', path)
    monkeypatch.setattr(cache, 'save_persistent_cache',
                        lambda c, p=path: open(p, 'w').write(json.dumps(c)))
    with cache.CACHE_LOCK:
        cache.store_entry('someone', {'status_code': S['deleted']})
    cache.flush_cache()
    assert json.load(open(path))['someone']['status_code'] == S['deleted']
