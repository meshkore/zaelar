"""Rows a worker writes as a JSON array reach the action's one list field (best-plumber-same-day ES, 2026-10-15).

The worker wrote its candidates to `rows.json` as an array; `widget_cli data results append @rows.json` died with
«el payload debe ser un objeto JSON», and a round went to rewrapping what `append {items: [...]}` could only have
meant. A list is wrapped only where the action declares exactly ONE list field; anywhere else it is still refused.
"""
import json

from nucleo import widget_cli as WC


def test_results_append_declares_one_list_field():
    assert WC._list_key("results", "append") == "items"


def test_an_array_file_becomes_that_field(tmp_path):
    f = tmp_path / "rows.json"
    f.write_text(json.dumps([{"title": "Fontanero Ruiz", "rating": "4,8"}]), encoding="utf-8")
    assert WC._read_payload(f"@{f}", "items") == {"items": [{"title": "Fontanero Ruiz", "rating": "4,8"}]}


def test_without_one_list_field_an_array_is_still_refused(tmp_path, capsys):
    f = tmp_path / "rows.json"
    f.write_text("[1, 2]", encoding="utf-8")
    assert WC._read_payload(f"@{f}") is None and "objeto JSON" in capsys.readouterr().out
