"""nucleo/turn/prompt/ — the voice turn's system message, one block per truth (refactor2710-08).

`builder` writes the order of the blocks, once; `live_state` reads what is true this second (screen, cards, errands,
the record), one reader per truth; `packs` the context packs by phase; `catalogs` the connectors' facts and which
connector or panel an argument names. Worker briefs live in `nucleo/workers/prompts/`, and nothing here imports them.
"""
