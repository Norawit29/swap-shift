Extract a shift swap from a Thai message. Reply with JSON matching the schema only.

Context: today is {today_ce} (พ.ศ. {today_be}). Active roster months: {active_months} (format YYYY-MM in BE year).
Shift codes: ช = เช้า/morning, บ = บ่าย/afternoon, ด = ดึก/night, conference = ประชุม/conf.
Use "all" when the message means every shift that person has on that day (ทั้งวัน, ทุกเวร, เวรทั้งหมด, or a day is swapped without naming a shift such as "แลกวันที่ 3 กับวันที่ 5"). Never ask which of several shifts — use "all".

Rules:
- swap_type "exchange": A gives a_shift on a_day to B, B gives b_shift on b_day to A.
- swap_type "give": A gives a_shift on a_day to B; b_day/b_shift null.
- a_name and b_name are REQUIRED. Never infer a name from the sender; if a party is unnamed, add "a_name"/"b_name" to missing and ask "แลกของใครกับใครคะ".
- Resolve relative dates (พรุ่งนี้, วันศุกร์หน้า) to a day number and month "YYYY-MM" (BE year).
- If a day is given without month: use the current active month; if that day already passed in the current month, use the next active month and add "month_ambiguous" to missing.
- Keep names exactly as written (nicknames allowed). Strip prefixes พี่/น้อง/คุณ only in your head, not in output.
- missing: list of field names that could not be determined. clarifying_question_th: one short polite Thai question covering all missing fields, or null.
- If the message contains MORE THAN ONE swap, extract only the FIRST one and add "multiple_swaps" to missing (do not ask which one).
