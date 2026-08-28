Extract a roster question. Reply with JSON matching the schema only.
Context: today is {today_ce} (พ.ศ. {today_be}). Active roster months: {active_months}.
name: person asked about (null if asking "who"). day: integer day (null if not given). month: "YYYY-MM" BE year (null = current).
shift: ช (เช้า), บ (บ่าย), ด (ดึก), conference, or null if not asked about a specific shift.
