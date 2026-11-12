from app.engines.apply_rules import classify_event, next_expected_seq


def test_next_expected():
    assert next_expected_seq(0) == 1
    assert next_expected_seq(4) == 5


def test_classify_apply_and_gap():
    event = {"seq": 1, "op": "upsert", "entity_key": "A", "event_ts": "t", "payload": {}}
    assert classify_event(event=event, cursor=0, already_applied=False) == "apply"
    gap = {"seq": 3, "op": "upsert", "entity_key": "A", "event_ts": "t", "payload": {}}
    assert classify_event(event=gap, cursor=1, already_applied=False) == "quarantine_gap"
    assert (
        classify_event(event=event, cursor=0, already_applied=True) == "skipped_duplicate"
    )
