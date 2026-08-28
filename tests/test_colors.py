from agent.sheets.colors import color_requests, person_colors
from agent.sheets.writer import CellWrite

RED, BLUE, WHITE = (1.0, 0.8, 0.8), (0.8, 0.8, 1.0), (1.0, 1.0, 1.0)


def test_person_colors_majority_ignores_white_and_tm():
    cells = {(4, 3): ("ศรี", RED), (8, 3): ("ศรี TM", RED), (9, 3): ("ศรี", BLUE), (4, 4): ("บี", BLUE),
             (5, 4): ("", WHITE), (6, 4): ("บี", WHITE)}
    assert person_colors(cells) == {"ศรี": RED, "บี": BLUE}


def test_color_requests_swap_and_clear():
    colors = {"ศรี": RED, "บี": BLUE}
    writes = [CellWrite("ศรี", 3, 4, 6, "ศรี", "บี TM"), CellWrite("บี", 5, 8, 5, "บี", "ศรี"),
              CellWrite("ศรี", 7, 9, 5, "ศรี", ""), CellWrite("x", 1, 2, 3, "", "ใหม่")]
    reqs = color_requests(99, writes, colors)
    assert len(reqs) == 3  # unknown person 'ใหม่' skipped
    bg = [r["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"] for r in reqs]
    assert bg[0] == {"red": 0.8, "green": 0.8, "blue": 1.0}   # cell now บี → blue
    assert bg[1] == {"red": 1.0, "green": 0.8, "blue": 0.8}   # cell now ศรี → red
    assert bg[2] == {"red": 1, "green": 1, "blue": 1}         # cleared → white
    rng = reqs[0]["repeatCell"]["range"]
    assert (rng["startRowIndex"], rng["startColumnIndex"], rng["sheetId"]) == (3, 5, 99)
