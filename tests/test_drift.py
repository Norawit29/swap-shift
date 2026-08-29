from agent.sheets.drift import replay_grid


def test_replay_grid_moves_codes_by_slot():
    planned = {("ธนดล", 3): "ช", ("จุฑามาศ", 10): "ช", ("ครองวงศ์", 20): "ชบ", ("จุฑามาศ", 13): "ชบ"}
    audit = [
        {"day": "10", "before": "จุฑามาศ", "after": "ธนดล", "slot": "ช"},
        {"day": "3", "before": "ธนดล", "after": "จุฑามาศ", "slot": "ช"},
        {"day": "20", "before": "ครองวงศ์", "after": "จุฑามาศ", "slot": "ช"},
        {"day": "20", "before": "ครองวงศ์", "after": "จุฑามาศ", "slot": "บ"},
        {"day": "13", "before": "จุฑามาศ", "after": "ครองวงศ์", "slot": "ช"},
        {"day": "13", "before": "จุฑามาศ", "after": "ครองวงศ์", "slot": "บ"},
        {"day": "12", "before": "", "after": "ธนดล", "slot": "ด"},          # edit: add
        {"day": "7", "before": "คมสันติ", "after": "", "slot": "ด"},         # edit: clear (not in planned → ignored)
        {"day": "9", "before": "x", "after": "y", "slot": ""},              # legacy row → skipped
    ]
    exp = replay_grid(planned, audit)
    assert exp == {("ธนดล", 10): "ช", ("จุฑามาศ", 3): "ช", ("จุฑามาศ", 20): "ชบ", ("ครองวงศ์", 13): "ชบ",
                   ("ธนดล", 12): "ด"}


def test_code_order_is_not_drift():
    from agent.sheets.drift import canon, replay_grid

    assert canon("ชดบ") == canon("ชบด") == "ชบด"
    assert canon("") == "" and canon("ด") == "ด"
    # replay emits canonical order, so it matches how the sheet's slots read back
    exp = replay_grid({("ครองวงศ์", 2): "ชด"}, [{"day": "2", "before": "คมสันติ", "after": "ครองวงศ์", "slot": "บ"}])
    assert exp[("ครองวงศ์", 2)] == "ชบด"
