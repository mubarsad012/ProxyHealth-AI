Extra detail for the instructions above. It changes none of their rules.

Worked example of one demand. Block p2b4 prints: Return the signed form by March 3, 2031.
- `kind`: deadline. `role`: response_due, because this paper asks for something back by that date. Choose each demand's own `role` from the list: a court or hearing date is hearing_date, a date to pay is payment_due, an appointment is appointment.
- `source_quote`: Return the signed form by March 3, 2031. These are the printed words themselves, one line or sentence copied from the paper.
- `value_verbatim`: March 3, 2031. Only the date, amount, phone number or short phrase inside `source_quote`, never the whole sentence.
- `date_text`: March 3, 2031.
- `span_ids`: p2b4. Block ids go here and nowhere else.
Never write a block id such as p1b3, or a transcript label such as [p1b3], in `source_quote`, `value_verbatim` or `date_text`. `red_flags` follow the same rule: the printed words in `source_quote`, the block ids in `span_ids`.

Write `summary_title` as a short label of at most 8 words, not a sentence. Do not start `clerk_need_en` with "I need help with"; the app adds those words.

Examples in these instructions only show the shape of an answer. Never copy an example's date, amount or details into your answer; every value you write comes from this paper.
