"""Submitted orders remain exposure for the recorder's duplicate BUY guards."""

import sqlite3
from unittest.mock import patch

import pytest

from bridge_recorder import BridgeTradeRecorder


class Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, parameters):
        self.cursor = self.connection.execute(sql.replace("%s", "?"), parameters)

    def fetchone(self):
        return self.cursor.fetchone()


class Connection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def cursor(self):
        return Cursor(self.database)


@pytest.mark.parametrize("status,expected", [
    ("PENDING", True),
    ("SUCCESS", True),
    ("SUBMITTED_UNVERIFIED", True),
    ("FAILED", False),
    ("SKIPPED", False),
])
def test_recorder_duplicate_guards_include_unconfirmed_submissions(status, expected):
    database = sqlite3.connect(":memory:")
    try:
        database.execute("CREATE TABLE bridge_trade_record (bridge_id TEXT, side TEXT, status TEXT, market_id TEXT, raw_payload TEXT)")
        recorder = BridgeTradeRecorder()
        database.execute("INSERT INTO bridge_trade_record VALUES (?, 'BUY', ?, 'market', ?)",
                         (recorder.bridge_id, status, '{"leaderAddress":"0xleader","marketSlug":"same-market"}'))
        with patch.object(recorder, "_connect", return_value=Connection(database)):
            assert recorder.has_prior_short_cycle_buy("market", "same-market", "0xLeader") is expected
            assert recorder.has_any_prior_short_cycle_buy("market", "same-market") is expected
    finally:
        database.close()
