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


def test_fuzzy_typo_single_candidate(staff):
    r = resolve("ศรีี", staff)  # extra vowel
    assert r.ok and r.staff.staff_id == "N001"  # caught by prefix stage
    r2 = resolve("บุศบา", staff)  # บุษบา misspelt
    assert r2.ok and r2.staff.staff_id == "N002"


def test_fuzzy_real_names():
    from agent.change.name_resolver import Staff

    names = ["ครองวงศ์", "ภควดี", "ธนดล", "คมสันติ", "ปวีณอร", "อรรถสิทธิ์", "ภัทรพล", "จุฑามาศ", "วรวรรธน์",
             "สุรีย์ภรณ์", "นรวิชญ์", "ขวัญศิริ", "สุธาพร", "ธนวัฒน์"]
    st = [Staff(n, n, (n,)) for n in names]
    assert resolve("ธนดน", st).staff.staff_id == "ธนดล"
    assert resolve("จุฑามาส", st).staff.staff_id == "จุฑามาศ"
    assert resolve("อรรถสิทธ์", st).staff.staff_id == "อรรถสิทธิ์"
    assert resolve("สุธาภร", st).staff.staff_id == "สุธาพร"
    assert not resolve("สมชาย", st).ok and not resolve("สมชาย", st).ambiguous  # nothing similar → not found
    assert not resolve("ธน", st).ok and resolve("ธน", st).ambiguous            # prefix stage still asks
