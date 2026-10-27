import collections
import datetime
import threading
import time

import pytest

from conftest import FakeResponse
from reddit_analyzer.api import accounts, arctic_shift, reddit_oauth
from reddit_analyzer.config import STATUS_CODES as S
from reddit_analyzer.core import cache


def to_base36(n):
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out


class FakeWorld:
    """250 accounts behind a fake Reddit OAuth API and a fake Arctic Shift.

    Every 50 accounts: #1 is suspended, #2 is left out of bulk answers (and
    404s per user), #3 has no account id in Arctic Shift. The rest are active.
    """

    def __init__(self):
        self.calls = collections.Counter()
        self.bulk_sizes = []
        self.bulk_status = 200
        self.accounts = {}
        for i in range(250):
            kind = {1: 'suspended', 2: 'omitted', 3: 'noid'}.get(i % 50, 'active')
            self.accounts[f'user{i}'] = {'id': to_base36(i + 1000), 'kind': kind,
                                         'created': 1420070400 + i * 86400}
        self.by_id = {v['id']: (k, v) for k, v in self.accounts.items()}

    # reddit_oauth._session
    def post(self, url, **kwargs):
        self.calls['token'] += 1
        return FakeResponse(200, {'access_token': 'tok', 'expires_in': 86400})

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith('/api/user_data_by_account_ids'):
            self.calls['bulk'] += 1
            ids = params['ids'].split(',')
            self.bulk_sizes.append(len(ids))
            if self.bulk_status != 200:
                return FakeResponse(self.bulk_status, {'error': 'nope'})
            out = {}
            for full in ids:
                name, v = self.by_id[full[3:]]
                if v['kind'] == 'omitted':
                    continue
                entry = {'name': name, 'created_utc': v['created']}
                if v['kind'] == 'suspended':
                    entry['is_suspended'] = True
                out[full] = entry
            return FakeResponse(200, out)
        self.calls['about'] += 1
        v = self.accounts.get(url.split('/user/')[1].split('/')[0])
        if v is None or v['kind'] == 'omitted':
            return FakeResponse(404, {'error': 404})
        return FakeResponse(200, {'data': {'created_utc': v['created'], 'is_suspended': v['kind'] == 'suspended'}})

    # arctic_shift
    def user_index(self, author):
        self.calls['arctic_index'] += 1
        v = self.accounts.get(author)
        if not v:
            return None, None, None
        return (None if v['kind'] == 'noid' else v['id']), datetime.date(2016, 1, 1), datetime.date(2025, 1, 1)

    def first_activity(self, author):
        self.calls['arctic_search'] += 1
        return None

    def expected_status(self, name):
        kind = self.accounts[name]['kind']
        return {'active': S['active'], 'suspended': S['suspended'], 'omitted': S['deleted'], 'noid': S['active']}[kind]


@pytest.fixture
def world(monkeypatch):
    fake = FakeWorld()
    monkeypatch.setattr(reddit_oauth, '_session', fake)
    monkeypatch.setattr(arctic_shift, 'fetch_user_index', fake.user_index)
    monkeypatch.setattr(arctic_shift, 'fetch_first_activity', fake.first_activity)
    reddit_oauth.set_credentials({'client_id': 'id', 'client_secret': 's', 'username': ''})
    return fake


def run_batch(names, cancel=None):
    got = {}
    finished = accounts.lookup_accounts(names, lambda u, info: got.__setitem__(u, info), cancel=cancel)
    return finished, got


def test_bulk_lookup_covers_100_accounts_per_request(world):
    finished, got = run_batch(list(world.accounts))
    assert finished and len(got) == 250
    assert world.calls['bulk'] == 3 and world.bulk_sizes == [98, 98, 49]   # only users with an id
    assert world.calls['about'] == 10              # 5 left out of bulk + 5 without an id
    assert world.calls['arctic_index'] == 250 and world.calls['arctic_search'] == 0
    for name, v in world.accounts.items():
        status, birth, _last, source = got[name]
        assert status == world.expected_status(name), name
        if v['kind'] == 'omitted':
            assert (birth, source) == ('2016-01-01', 'Estimated')
        else:
            expected = datetime.datetime.fromtimestamp(v['created'], datetime.timezone.utc).strftime('%Y-%m-%d')
            assert (birth, source) == (expected, 'True')


def test_cached_accounts_need_no_requests(world):
    names = list(world.accounts)
    run_batch(names)
    world.calls.clear()
    finished, got = run_batch(names)
    assert finished and len(got) == 250 and not world.calls


def test_refused_bulk_endpoint_falls_back_to_per_user(world):
    world.bulk_status = 403
    finished, got = run_batch(list(world.accounts))
    assert finished
    assert world.calls['bulk'] == 1 and not reddit_oauth.bulk_available()
    assert world.calls['about'] == 250
    # Arctic Shift: the first chunk was fetched for bulk; after that only for accounts Reddit gave no date
    assert world.calls['arctic_index'] == 100 + 3
    assert all(got[n][0] == world.expected_status(n) for n in world.accounts)
    reddit_oauth.set_credentials({'client_id': 'id', 'client_secret': 's', 'username': ''})
    assert reddit_oauth.bulk_available()


def test_bulk_entry_with_wrong_name_is_checked_per_user(world, monkeypatch):
    real_get = world.get

    def renamed(url, params=None, **kwargs):
        resp = real_get(url, params=params, **kwargs)
        if url.endswith('/api/user_data_by_account_ids'):
            for entry in resp._payload.values():
                entry['name'] = 'someone_else'
        return resp
    monkeypatch.setattr(world, 'get', renamed)
    run_batch(['user0', 'user4'])
    assert world.calls['about'] == 2


def test_cancel_stops_a_batch_early(monkeypatch):
    monkeypatch.setattr(accounts, '_fetch_reddit_about', lambda a: (time.sleep(0.05), (None, None))[1])
    monkeypatch.setattr(arctic_shift, 'fetch_user_index', lambda a: (None, None, None))
    monkeypatch.setattr(arctic_shift, 'fetch_first_activity', lambda a: None)
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    started = time.time()
    finished, got = run_batch([f'u{i}' for i in range(250)], cancel)
    assert not finished and len(got) < 250 and time.time() - started < 1.5


def test_public_api_is_skipped_after_a_refusal(monkeypatch):
    requests_made = []

    def refuse(author):
        requests_made.append(author)
        return None, 429
    monkeypatch.setattr(accounts, '_fetch_about_json', refuse)
    monkeypatch.setattr(arctic_shift, 'fetch_user_index', lambda a: (None, datetime.date(2019, 3, 11), None))
    infos = [accounts.get_account_info(f'u{i}') for i in range(5)]
    assert requests_made == ['u0']
    assert all(info == (S['unknown'], '2019-03-11', 'Unknown', 'Estimated') for info in infos)
    assert cache.CACHE['u3']['checked_with_oauth'] is False


def test_failed_lookup_without_any_date_is_not_cached(monkeypatch):
    monkeypatch.setattr(accounts, '_fetch_reddit_about', lambda a: (None, None))
    monkeypatch.setattr(arctic_shift, 'fetch_user_index', lambda a: (None, None, None))
    monkeypatch.setattr(arctic_shift, 'fetch_first_activity', lambda a: None)
    assert accounts.get_account_info('nobody') == accounts.UNKNOWN_INFO
    assert 'nobody' not in cache.CACHE


@pytest.mark.parametrize('birth, source, text', [
    ('2015-01-01', 'True', '2015-01-01'),
    ('2019-03-11', 'Estimated', '≤ 2019-03-11 (first activity)'),
    ('Unknown', 'Unknown', 'Unknown'),
    ('', 'True', 'Unknown'),
])
def test_describe_creation_date(birth, source, text):
    assert accounts.describe_creation_date(birth, source) == text
