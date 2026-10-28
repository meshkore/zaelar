"""A repaired call presents the sheet it lands on, never the bare base (demo pass 133, 2026-10-15, S1→S3).

«so how did the monitors go, show me»: the model promised without a call; the voice repair ran `results:present` —
which lands on the errand's sheet — but first presented the BARE `results` id, so an empty base card opened beside the
sheet. With two `results` cards open, «compare them side by side» and «open the one that's the best deal» went to
the empty base, and the detail never opened. The repair now presents `card_to_present(...)`, the same narrowing the
verdict's own show uses (2b4094d3).
"""




def test_the_base_narrows_to_the_open_sheet(monkeypatch):
    import server.voice_api as va
    from nucleo.flash import direct_action as DA
    monkeypatch.setattr(va, "open_instances", lambda: ["results::b54bca-ls1"])
    assert DA.card_to_present("results", "so how did the monitors go, show me") == "results::b54bca-ls1"
