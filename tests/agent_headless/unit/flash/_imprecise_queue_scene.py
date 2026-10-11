"""The queue of use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11), shared by nodes 2.490-2.494.

Five rows, so «el penúltimo» is row 4 and «el último» row 5; «skills» is a word only row 1 carries."""
from __future__ import annotations

QUEUE = ["Diego Maradona 👑 Prime Argentina Skills, Goals, Dribbling & Tricks", "Opus - Live Is Life | Maradona 1989",
         "Los Goles Inolvidables de Diego Maradona", "Maradona - Anubiis x Hades 66 (Video Oficial)",
         "Maradona The Most Creative and Unpredictable"]
#: His sentence, verbatim from the report.
SAID = "el último… no, el penúltimo, ponlo justo después del de skills"
#: What it means: row 4 goes right behind row 1.
MOVED = [QUEUE[0], QUEUE[3], QUEUE[1], QUEUE[2], QUEUE[4]]
