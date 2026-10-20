from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pydantic import AliasChoices, BaseModel, Field
import pymol2
import pytest
from PySide6.QtWidgets import QApplication

from ms_components.ms_pymol import PymolControlBar, PymolPresetSpec, PymolSceneContext


@pytest.fixture
def grid_scene():
    app = QApplication.instance() or QApplication(["molsuite-pymol-grid-test"])
    with pymol2.PyMOL() as session:
        cmd = session.cmd
        for obj, slot, title in (
            ("rec_7", 1, "Target A"),
            ("lig_7", 1, "Ligand"),
            ("rec_9", 3, "Target B"),
            ("lig_9", 3, "Ligand"),
        ):
            cmd.pseudoatom(obj)
            cmd.set("grid_slot", slot, obj)
            cmd.set_title(obj, 1, title)
        bar = PymolControlBar(cmd)
        yield bar, cmd
        bar.close()
        app.processEvents()


def _labels(cmd, obj):
    labels = []
    cmd.iterate(obj, "labels.append(label)", space={"labels": labels})
    return labels


def test_offtarget_labels_use_titles_and_share_the_complex_slot(grid_scene):
    bar, cmd = grid_scene
    bar.set_scene_context("offtarget")

    assert cmd.get_setting_int("grid_mode") == 1
    assert _labels(cmd, "panel_text1") == ["Target A + Ligand"]
    assert _labels(cmd, "panel_text3") == ["Target B + Ligand"]
    for slot in (1, 3):
        obj = f"panel_text{slot}"
        assert cmd.get_setting_int("grid_slot", obj) == slot
        assert cmd.get_setting_int("label_relative_mode", obj) == 1
        assert cmd.get_setting_tuple("label_screen_point", obj)[1] == (-1.0, 1.0, 0.0)
        assert cmd.get_setting_tuple("label_position", obj)[1] == (1.0, -1.0, 0.0)
        assert cmd.get_setting_float("label_size", obj) == 14
        assert cmd.get("label_color", obj) == "front"


def test_grid_titles_can_be_updated_without_recreating_or_restyling(grid_scene):
    bar, cmd = grid_scene
    bar.set_scene_context("offtarget", grid_labels={1: "Complex A", 3: "Complex B"})
    cmd.set("label_size", 22, "panel_text1")
    title = "Complex 'quoted' \\ name\nnext line"
    bar.set_scene_context(PymolSceneContext(kind="offtarget", grid_labels={1: title}))

    assert _labels(cmd, "panel_text1") == [title]
    assert cmd.count_atoms("panel_text1") == 1
    assert cmd.get_setting_float("label_size", "panel_text1") == 22
    assert "panel_text3" not in cmd.get_names("objects")
    assert "rec_9" in cmd.get_names("objects")


def test_grid_labels_are_recreated_after_the_scene_is_cleared(grid_scene):
    bar, cmd = grid_scene
    bar.set_scene_context("offtarget", grid_labels={1: "First"})
    cmd.delete("all")
    bar.set_scene_context("offtarget", grid_labels={3: "Next"})

    assert cmd.get_names("objects") == ["panel_text3"]
    assert _labels(cmd, "panel_text3") == ["Next"]
    assert cmd.get_setting_int("grid_slot", "panel_text3") == 3


@pytest.mark.parametrize("kind", ["generic", "receptor", "ligand", "complex", "docking_pose"])
def test_leaving_offtarget_disables_grid_and_removes_only_its_labels(grid_scene, kind):
    bar, cmd = grid_scene
    cmd.pseudoatom("user_annotation", label="Keep me")
    bar.set_scene_context("offtarget", grid_labels={1: "Complex"})
    bar.set_scene_context(kind)

    assert cmd.get_setting_int("grid_mode") == 0
    assert "panel_text1" not in cmd.get_names("objects")
    assert _labels(cmd, "user_annotation") == ["Keep me"]
    assert cmd.count_atoms("rec_7 or lig_7 or rec_9 or lig_9") == 4


def test_other_contexts_do_not_override_an_unrelated_grid(grid_scene):
    bar, cmd = grid_scene
    cmd.set("grid_mode", 2)
    bar.set_scene_context("receptor")
    assert cmd.get_setting_int("grid_mode") == 2


def test_automatic_grid_labels_fall_back_to_object_names(grid_scene):
    bar, cmd = grid_scene
    cmd.set_title("rec_7", 1, "")
    bar.set_scene_context("offtarget", target="rec_7")
    assert _labels(cmd, "panel_text1") == ["rec_7"]
    assert "panel_text3" not in cmd.get_names("objects")


def test_grid_label_name_collisions_are_reported_without_overwriting(grid_scene):
    bar, cmd = grid_scene
    cmd.pseudoatom("panel_text1", label="User text")
    errors = []
    bar.command_failed.connect(errors.append)
    bar.set_scene_context("offtarget", grid_labels={1: "Complex"})

    assert errors == ["Grid labels: Grid label object 'panel_text1' already exists."]
    assert _labels(cmd, "panel_text1") == ["User text"]
    bar.set_scene_context("generic")
    assert _labels(cmd, "panel_text1") == ["User text"]


def test_presets_restore_grid_labels_hidden_by_global_representation_changes(grid_scene):
    bar, cmd = grid_scene
    bar.set_scene_context("offtarget", grid_labels={1: "Complex"})
    bar.register_preset(PymolPresetSpec(
        key="test.hide_all",
        label="Hide all",
        callback=lambda cmd, context: cmd.hide("everything", "all"),
    ))
    calls = []
    original_show = cmd.show
    cmd.show = lambda *args, **kwargs: (calls.append(args), original_show(*args, **kwargs))[1]
    bar.apply_preset("test.hide_all")

    assert ("labels", "panel_text1") in calls
    assert _labels(cmd, "panel_text1") == ["Complex"]
    assert cmd.count_atoms("panel_text1") == 1
