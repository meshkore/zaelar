"""A picture errand's worker is told the viewer is the deliverable, searches IMAGES and gets no ≥40-row hunt (2.502).

show-real-photo-of-a-new-car__us (2026-10-11): the worker was handed a research brief asking for ≥40 candidates,
every `use_tool` search ran on the fact route (23 web searches, no image search) and the deliverable contract said
nothing about the viewer he was looking at.
"""
from __future__ import annotations

import inspect
import types

from nucleo import dispatch_prompts, picture_errand, surfaces

from nucleo.dispatch import session_steps as dispatch_session_steps


def test_the_prompt_names_the_viewer_only_for_pictures():
    assert picture_errand.PICTURES_BLOCK in dispatch_prompts.trusted_blocks(surfaces.IMAGES)
    assert picture_errand.PICTURES_BLOCK not in dispatch_prompts.trusted_blocks(surfaces.LIST)
    assert dispatch_prompts.DOC_SURFACE_BLOCK in dispatch_prompts.trusted_blocks(surfaces.DOC)


def test_its_searches_run_on_the_image_module():
    assert picture_errand.search_route(types.SimpleNamespace(surface=surfaces.IMAGES)) == "images"
    assert picture_errand.search_route(types.SimpleNamespace(surface=surfaces.LIST)) == "inline_fact"


def test_no_research_brief_is_composed_for_pictures():
    src = inspect.getsource(dispatch_session_steps.build_what_it_runs_with)
    assert 'not _dev and not _ds._d.surfaces.delivers_pictures(getattr(rec, "surface", ""))' in src
