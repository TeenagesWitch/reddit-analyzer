from reddit_analyzer import paths


def test_moves_legacy_files_into_data_dir(tmp_path):
    old = tmp_path / 'old'
    old.mkdir()
    (old / 'creation_cache.json').write_text('{"a": 1}')
    (old / 'skip_list.txt').write_text('bot\n')
    data = tmp_path / 'data'

    moved = paths.move_legacy_data_files(data, [old])

    assert sorted(moved) == ['creation_cache.json', 'skip_list.txt']
    assert (data / 'creation_cache.json').read_text() == '{"a": 1}'
    assert not (old / 'creation_cache.json').exists()
    assert not (data / 'reddit_credentials.json').exists()


def test_never_overwrites_files_already_in_data_dir(tmp_path):
    old = tmp_path / 'old'
    old.mkdir()
    (old / 'skip_list.txt').write_text('old\n')
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'skip_list.txt').write_text('new\n')

    assert paths.move_legacy_data_files(data, [old]) == []
    assert (data / 'skip_list.txt').read_text() == 'new\n'
    assert (old / 'skip_list.txt').read_text() == 'old\n'


def test_first_folder_with_the_file_wins(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    for folder, text in ((first, 'first'), (second, 'second')):
        folder.mkdir()
        (folder / 'creation_cache.json').write_text(text)
    data = tmp_path / 'data'

    paths.move_legacy_data_files(data, [first, second])

    assert (data / 'creation_cache.json').read_text() == 'first'
    assert (second / 'creation_cache.json').exists()


def test_tests_use_the_override_folder():
    # conftest points the data folder at a temp dir; nothing may resolve to the real project data/
    assert paths.DATA_DIR != paths.app_dir() / 'data'
