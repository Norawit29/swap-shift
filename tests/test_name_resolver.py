from agent.change.name_resolver import normalize, resolve


def test_normalize_strips_prefix():
    assert normalize("พี่ศรี") == "ศรี"
    assert normalize("คุณพี่ ศรี ") == "ศรี"
    assert normalize("น้อง บี") == "บี"


def test_exact_nickname(staff):
    r = resolve("พี่ศรี", staff)
    assert r.ok and r.staff.staff_id == "N001"


def test_full_name_and_first_name(staff):
    assert resolve("สมศรี ใจดี", staff).staff.staff_id == "N001"
    assert resolve("บุษบา", staff).staff.staff_id == "N002"


def test_ambiguous_never_guesses(staff):
    # 'ศรีว' prefix-matches ศรีวรรณ only; 'ศ' would match ศรี + ศรีวรรณ
    r = resolve("ศ", staff)
    assert r.ambiguous and {s.staff_id for s in r.matches} == {"N001", "N004"}
    assert not r.ok


def test_not_found_and_inactive(staff):
    assert not resolve("มานี", staff).ok and not resolve("มานี", staff).ambiguous
    assert not resolve("เก่า", staff).ok  # inactive excluded
    assert not resolve("", staff).ok
