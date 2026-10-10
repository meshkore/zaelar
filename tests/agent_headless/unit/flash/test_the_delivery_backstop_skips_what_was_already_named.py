"""The delivery backstop names rows nobody named yet — not the three he already turned down (V2-781 T521, 2026-10-10).

Monitor pair ES: the operator had rejected three rows by name («el Dell P2017H es de 20"», «el LEPU es de paciente»);
the backstop read only the sheet's TOP three and only zaelar's own lines as «already said», so it announced those
same three again — while four rows that met the criterion sat further down. Rows he named count as said, and the
backstop reads deeper than the top three to find three that are new.
"""
from __future__ import annotations


def test_rows_he_named_are_not_new_and_deeper_rows_surface(monkeypatch):
    from nucleo.flash import delivery as D, live_blocks as LB
    rows = ["Dell P2017H 20\" — 89 €", "LEPU Monitor Paciente — 120 €", "LCD 10,1\" Portátil — 60 €",
            "Lenovo L27h-4A — 168,75 €", "LG UltraFine 27US500-W — 175 €", "Philips Evnia 27M2C5501 — 159,90 €"]
    monkeypatch.setattr(LB, "any_live_task_rows", lambda n=3: ("monitor 27 pulgadas", rows[:n]))
    monkeypatch.setattr(LB, "any_stalled_task", lambda: ("", 0, ""))
    window = [{"role": "user", "content": "El Dell P2017H es de 20, el LEPU es de paciente y el LCD 10,1 es portátil."},
              {"role": "assistant", "content": "Vale, los descarto."}]
    out = D.apply_to_reply("Sigo buscando, te aviso.", window)
    assert "Lenovo" in out and "Dell" not in out and "LEPU" not in out, out
