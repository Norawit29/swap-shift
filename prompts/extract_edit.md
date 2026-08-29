Extract a single-cell roster edit from a Thai message. Reply with JSON matching the schema only.

Context: today is {today_ce} (พ.ศ. {today_be}). Active roster months: {active_months}.
new_shift: one of ช, บ, ด, conference, or "" (empty string) for off/หยุด/ว่าง. null if not stated.
target_name as written. day as integer. A slash date is DAY/MONTH: "4/9" = day 4 month 09. month "YYYY-MM" BE year (default current active month).
missing: field names not determinable; clarifying_question_th: one short Thai question or null.
