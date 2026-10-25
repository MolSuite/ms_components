from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pydantic import AliasChoices, BaseModel, Field
import pymol2
import pytest
from PySide6.QtWidgets import QApplication

from ms_components.ms_pymol import COMPARISON_COLORS, PymolControlBar, PymolPresetSpec, PymolSceneContext


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
            cmd.pseudoatom(obj, elem="C")
            cmd.set("grid_slot", slot, obj)
            cmd.set_title(obj, 1, title)
        bar = PymolControlBar(cmd)
        yield bar, cmd
        bar.close()
        app.processEvents()


@pytest.mark.parametrize("clicks", [0, 1, 2])
def test_hydrogen_modes_apply_globally_and_to_new_systems(grid_scene, clicks, monkeypatch):
    bar, cmd = grid_scene
    cmd.fragment("gly", "ligand")
    cmd.fragment("gly", "other_ligand")
    cmd.show("sticks", "ligand or other_ligand")
    cmd.select("sele", "ligand and elem C")
    bar.set_scene_context("ligand", target="ligand")
    atom_count = cmd.count_atoms("all")
    heavy_count = cmd.count_atoms("not hydro and rep sticks")
    for _ in range(clicks):
        bar.hydrogens_action.trigger()

    def check(obj):
        expected = (0 if clicks == 0 else cmd.count_atoms(
            f"{obj} and hydro" + (" and neighbor (elem N+O+S)" if clicks == 2 else "")
        ))
        assert cmd.count_atoms(f"{obj} and hydro and visible") == expected
        if clicks == 2:
            assert 0 < expected < cmd.count_atoms(f"{obj} and hydro")

    check("ligand")
    check("other_ligand")
    assert cmd.count_atoms("not hydro and rep sticks") == heavy_count
    assert cmd.count_atoms("all") == atom_count
    cmd.fragment("cys", "new_system")
    cmd.show("spheres", "new_system")
    bar.apply_hydrogen_visibility()  # Same hook used immediately before the viewer draws.
    check("new_system")
    bar.set_scene_context("ligand", target="new_system")
    bar.apply_representation("sticks")
    check("new_system")
    bar.register_preset(PymolPresetSpec(
        key="test.show_all", label="Show all", callback=lambda cmd, _: cmd.show("lines", "all")
    ))
    bar.apply_preset("test.show_all")
    check("ligand")
    check("new_system")
    calls = []
    monkeypatch.setattr(cmd, "hide", lambda *args: calls.append(args))
    monkeypatch.setattr(cmd, "show", lambda *args: calls.append(args))
    assert bar.apply_hydrogen_visibility()
    assert calls == []  # Repeated renders must not invalidate PyMOL's scene again.


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
        assert cmd.get("label_color", obj) == COMPARISON_COLORS[slot - 1]
        assert cmd.get("label_outline_color", obj) == "front"


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


def test_comparison_layout_menu_preserves_camera_and_groups(grid_scene):
    bar, cmd = grid_scene
    assert not bar.comparison_menu.menuAction().isVisible()
    bar.set_scene_context("comparison", grid_labels={1: "Complex A", 3: "Complex B"})
    assert bar.comparison_menu.menuAction().isVisible()
    objects = set(cmd.get_names("objects"))
    cmd.turn("y", 20)
    view = cmd.get_view()
    bar._comparison_layout_actions["overlay"].trigger()

    assert bar.comparison_layout == "overlay"
    assert cmd.get_setting_int("grid_mode") == 0
    assert cmd.get_setting_int("grid_slot", "rec_9") == 3
    assert cmd.get_setting_int("grid_slot", "lig_9") == 3
    first = cmd.get_setting_tuple("label_screen_point", "panel_text1")[1]
    second = cmd.get_setting_tuple("label_screen_point", "panel_text3")[1]
    assert first[1] > second[1]
    assert cmd.get_view() == pytest.approx(view)
    assert set(cmd.get_names("objects")) == objects

    bar.set_scene_context("comparison", grid_labels={1: "Updated A", 3: "Complex B"})
    assert cmd.get_setting_int("grid_mode") == 0
    assert _labels(cmd, "panel_text1") == ["Updated A"]
    bar._comparison_layout_actions["grid"].trigger()
    assert cmd.get_setting_int("grid_mode") == 1
    assert cmd.get_setting_tuple("label_screen_point", "panel_text3")[1] == first
    assert cmd.get_view() == pytest.approx(view)
    bar.set_scene_context("generic")
    assert not bar.comparison_menu.menuAction().isVisible()
    assert cmd.get_setting_int("grid_mode") == 0


@pytest.mark.parametrize("layout", ["grid", "overlay"])
def test_comparison_colors_match_receptor_ligand_and_label_without_recoloring_oxygen(grid_scene, layout):
    bar, cmd = grid_scene
    cmd.pseudoatom("rec_7", elem="O")
    cmd.color("red", "rec_7 and elem O")
    bar.set_scene_context("comparison")
    bar.set_comparison_layout(layout)

    for obj, slot in (("rec_7", 1), ("lig_7", 1), ("rec_9", 3), ("lig_9", 3)):
        color = COMPARISON_COLORS[slot - 1]
        colors = set()
        cmd.iterate(f"{obj} and elem C", "colors.add(color)", space={"colors": colors})
        assert colors == {cmd.get_color_index(color)}
        assert cmd.get("cartoon_color", obj) == color
        assert cmd.get("label_color", f"panel_text{slot}") == color
        assert cmd.get("label_outline_color", f"panel_text{slot}") == "front"
    oxygen = set()
    cmd.iterate("rec_7 and elem O", "colors.add(color)", space={"colors": oxygen})
    assert oxygen == {cmd.get_color_index("red")}


@pytest.mark.parametrize("layout", ["grid", "overlay"])
def test_generic_comparison_replacement_keeps_layout_camera_alignment_and_label_size(grid_scene, layout):
    bar, cmd = grid_scene
    cmd.set_name("rec_7", "structure_alpha")
    cmd.set_name("lig_7", "pose_alpha")
    bar.set_scene_context("comparison", grid_labels={1: "Alpha", 3: "Beta"})
    bar.set_comparison_layout(layout)
    cmd.set("label_size", 22, "panel_text1")
    cmd.translate([5, 6, 7], object="structure_alpha", camera=0)
    cmd.turn("y", 15)
    cmd.set("auto_zoom", 2)
    view = cmd.get_view()
    objects = set(cmd.get_names("objects"))
    data = b"HETATM    1  C1  LIG A   1       4.000   0.000   0.000  1.00  0.00           C\nEND\n"
    assert bar.replace_comparison_object("pose_alpha", data, "pdb", reference="structure_alpha", label="Alpha [P2]")

    assert cmd.get_setting_int("grid_mode") == int(layout == "grid")
    assert cmd.get_setting_int("auto_zoom") == 2
    assert cmd.get_view() == pytest.approx(view)
    assert set(cmd.get_names("objects")) == objects
    assert cmd.get_setting_int("grid_slot", "pose_alpha") == 1
    assert cmd.get_object_matrix("pose_alpha") == pytest.approx(cmd.get_object_matrix("structure_alpha"))
    assert _labels(cmd, "panel_text1") == ["Alpha [P2]"]
    assert _labels(cmd, "panel_text3") == ["Beta"]
    assert cmd.get_setting_float("label_size", "panel_text1") == 22


def test_a_failed_comparison_load_keeps_the_old_object_and_restores_auto_zoom(grid_scene, monkeypatch):
    bar, cmd = grid_scene
    bar.set_scene_context("comparison", grid_labels={1: "Original"})
    original = cmd.get_coords("lig_7").copy()
    cmd.set("auto_zoom", 2)
    objects = set(cmd.get_names("objects"))
    errors = []
    bar.command_failed.connect(errors.append)

    def fail(*args):
        raise ValueError("Cannot read pose")

    monkeypatch.setattr(cmd, "load_raw", fail)
    assert not bar.replace_comparison_object("lig_7", b"invalid", "pdb", reference="rec_7", label="Replacement")
    assert cmd.get_coords("lig_7") == pytest.approx(original)
    assert cmd.get_setting_int("auto_zoom") == 2
    assert set(cmd.get_names("objects")) == objects
    assert _labels(cmd, "panel_text1") == ["Original"]
    assert errors == ["Replace comparison object: Cannot read pose"]


def test_comparison_layout_validation_does_not_change_unrelated_scenes(grid_scene):
    bar, cmd = grid_scene
    cmd.set("grid_mode", 2)
    with pytest.raises(ValueError, match="Unsupported comparison layout"):
        bar.set_comparison_layout("unknown")
    with pytest.raises(ValueError, match="comparison scene is required"):
        bar.set_comparison_layout("overlay")
    assert cmd.get_setting_int("grid_mode") == 2


def test_presets_keep_comparison_colors_and_the_overlay_layout(grid_scene):
    bar, cmd = grid_scene
    bar.set_scene_context("comparison")
    bar.set_comparison_layout("overlay")
    bar.register_preset(PymolPresetSpec(
        key="test.color_all", label="All white",
        callback=lambda cmd, context: cmd.color("white", "all"),
    ))
    bar.apply_preset("test.color_all")
    assert cmd.get_setting_int("grid_mode") == 0
    assert cmd.get("cartoon_color", "rec_9") == COMPARISON_COLORS[2]
    assert cmd.get("label_color", "panel_text3") == COMPARISON_COLORS[2]


def test_overlay_legend_spacing_follows_the_viewport_height(grid_scene, monkeypatch):
    bar, cmd = grid_scene
    bar.set_scene_context("comparison")
    bar.set_comparison_layout("overlay")
    monkeypatch.setattr(cmd, "get_viewport", lambda: (640, 480))
    bar._position_comparison_labels()
    large = cmd.get_setting_tuple("label_screen_point", "panel_text3")[1][1]
    monkeypatch.setattr(cmd, "get_viewport", lambda: (640, 240))
    bar._position_comparison_labels()
    small = cmd.get_setting_tuple("label_screen_point", "panel_text3")[1][1]
    assert 1 - small == pytest.approx(2 * (1 - large))
