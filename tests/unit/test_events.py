from dj.events import EventLog


def test_event_log_is_append_only_jsonl(tmp_path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    log.append("one", value=1)
    log.append("two", value=2)
    assert [event["type"] for event in log.read()] == ["one", "two"]

