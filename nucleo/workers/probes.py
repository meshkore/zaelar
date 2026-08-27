"""Telling a worker READING THE MENU apart from a worker that broke something.

Measured 2026-08-28 on `weekend-plan-barcelona__es`: the round was filed with two `error_interno` anomalies
and the judge wrote that «the worker failed technically to extract the price». What the worker had actually
done was run `nav_cli` and `worker_bridge` with no subcommand — argparse answers with a usage block and
**exit code 2**, so a discovery probe reaches us wearing the exact clothes of a crash. Two of the round's four
flagged failures were the model looking at the menu, and the mechanism score paid for them.

This is the instrument accusing the product, which is the one mistake a measuring tool may never make: a
false failure sends a fixing agent after something that never happened, and it costs more than the defect.

THE RULE, and why this one and not "exit code 2 is fine":

    the missing argument is `cmd` ITSELF  →  nobody chose a subcommand  →  someone is reading the menu.

A wrong argument to a REAL subcommand (`nav_cli click` with no ref) still says «arguments are required» and
still exits 2, and that one IS a broken call: an order was placed and it could not be served. Downgrading
every exit-2 would have hidden it. And the bridge has to be OURS — a foreign CLI complaining about its own
`cmd` argument is not something we know anything about.

What this does NOT claim: that probing is free. Four round-trips to read a menu the prompt already spells out
in full (`dispatch_prompts` lists every `nav_cli` subcommand and closes with «esos son TODOS los que
existen») is wasted time on a 496 s round. That is conduct, and conduct is measured, not silenced — it just
must not be measured as a CRASH.
"""
from __future__ import annotations

#: Los puentes que servimos nosotros. Un `usage:` de otro binario no lo sabemos interpretar y se deja como está.
OUR_BRIDGES = ("nav_cli", "worker_bridge", "widget_cli")


def is_menu_probe(text: str) -> bool:
    """True when this tool output is a worker LOOKING at one of our bridges, not failing at it."""
    low = " ".join((text or "").split()).lower()
    if "usage:" not in low or "arguments are required" not in low:
        return False
    if not any(b in low for b in OUR_BRIDGES):
        return False
    # `…required: cmd` y nada más. Si falta OTRO argumento, alguien sí eligió subcomando y la llamada está rota.
    tras = low.split("arguments are required:", 1)[1].strip()
    return tras.split()[0].rstrip(",") == "cmd" if tras.split() else False
