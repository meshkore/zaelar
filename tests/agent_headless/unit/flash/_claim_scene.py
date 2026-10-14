"""The shortlist rounds of 2026-10-14 (healthy chain) as data, shared by nodes 2.686-2.692 (`nucleo/flash/row_claims`).

Sheets in `claim_sheets/` are the ones each claim was made over: recorded from the sandbox (phone, sofa) or rebuilt
from the turn's own prompt and extraction (washer, TV, ski — a later sheet rewrite dropped those rows; each file's
`_source` says which). Replies are verbatim from the reports. `review` runs with injected sources, no disk.
"""
from __future__ import annotations

import json
from pathlib import Path

from nucleo.flash import claim_backing as B
from nucleo.flash import row_claims as R

SHEETS = Path(__file__).resolve().parent / "claim_sheets"
RECORDED = Path(__file__).resolve().parents[3] / "search" / "fixtures" / "sheets"


def rows(*names: str) -> list[dict]:
    out: list[dict] = []
    for n in names:
        out += B.rows_of(json.loads((SHEETS / f"{n}.json").read_text(encoding="utf-8")))
    return out


def review(reply: str, heard: str = "", *, sheets=(), evidence=(), window=None, errand: bool = True) -> dict:
    return R.review(reply, window, heard, rows=rows(*sheets), evidence=list(evidence), goals="", errand=errand)


def said(reply: str, heard: str = "", **kw) -> str:
    return " ".join(review(reply, heard, **kw)["parts"])


# search-buy-phone__us t5/t6 — the row was «iphone 17 256gb — 699», every hard fact «?».
PHONE_HEARD_NEW = "wait is the 699 one new? I said new."
PHONE_NEW = ("Yes, the 699 listing is new and unused — it's the standard iPhone 17 with 256 GB, not refurbished or an "
             "open-box unit. Actually, there are already candidates on the results sheet: «Apple iPhone 17, Verde "
             "salvia… — 971.1».")
PHONE_HEARD_AVAILABLE = ("The 699 one is better — those others aren’t the standard iPhone 17 except the verde salvia, "
                         "and that’s more. Is the 699 still available?")
PHONE_AVAILABLE = ("Yes — the iPhone 17 256GB at 699 is still available. Right now: Broad price sweep done (Phone House "
                   "929, PcComponentes 969, Fnac 1041, Amazon 1075, MediaMarkt 929). Verifying each on the retailer's "
                   "own page now.")
PHONE_STEP = "Broad price sweep done (Phone House 929, PcComponentes 969, Fnac 1041, Amazon 1075, MediaMarkt 929)."

# search-buy-washing-machine__es t8 — the reply as the model wrote it, before `row_check` appended its line.
WASHER_HEARD = ("Oye, la Balay y la SVAN se pasan de 400, esas fuera. La Evvo Terra de 329 sí está dentro, pero dime: "
                "¿esa es de 8 kilos y clase A? Confírmamelo, que no quiero otra sorpresa.")
WASHER_YES = ("Sí, la Evvo Terra de 329 es de 8 kilos y clase A. Y confirmado: la Balay y la SVAN quedan fuera por "
              "pasarse de 400.")

# search-buy-sofa__us t1 — the claim WAS backed: the listing's own title said «Only 6 Months Used».
SOFA_HEARD = "I'm in San Francisco, as long as it's within like 20 miles that works."
SOFA = ("I found eight sofas, ranging from free up to $350, all in the Bay Area. The most promising looks like the "
        "premium 3-seat sofa, only six months used at $350, or the Danish-style apartment sofa at $249.")

# search-buy-tv__us t2/t10 and search-buy-ski-gear__us t2 — rows ON the sheet at that turn (judged «in no source»
# because a later rewrite dropped them).
TV = ("Yes — it's pulling up options now. Best so far: a 55-inch Sansui 4K OLED at $649.99, an LG 55-inch 4K at $759, "
      "and a Sony Bravia XR A75L at $850.")
TV_924 = "Actually, there are already candidates on the results sheet: «Sansui 55\" UHD OLED Google TV… — 924»."
SKI_KORE = ("Actually, there are already candidates on the results sheet: «Esquís escaper Rossignol Blackops… — 303.56»; "
            "«Esquís Head Kore 99 All Mountain… — 208.69».")

# search-buy-ski-gear__us t8 — the notice pushed into his turn, and the reply that skipped it.
SKI_NOTICE_TURN = (
    "[SISTEMA] Brain worker · Tarea completada: Done — the shortlist is on screen in the document sheet.\n"
    "[SISTEMA] Aviso para el operador (zaelar): The shortlist is done and on your screen. Best pick is a Nordica "
    "Nemesis 161 with Dynafit bindings in Oakland for $150. Díselo con tus palabras DESPUÉS de contestar a lo que te "
    "ha pedido — todavía no lo sabe.\n\nwait, you told me earlier there was a listing called Alpine Touring Gear on "
    "geartrade. now you're saying you can't see it? yeah re-run it, and make sure whatever you shortlist actually "
    "has bindings and is under 400")
SKI_SKIPPED = ("You're right to call that out — I misspoke on that one. Let me re-run it properly and hold every "
               "candidate to the two rules: bindings actually mounted, and under four hundred.")
