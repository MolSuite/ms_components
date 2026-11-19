"""A project's folder is what a path parser can carry, whatever its author named it."""
from pathlib import Path

import pytest

from ms_components.ms_projects.naming import folder_for, folder_name


@pytest.mark.parametrize("name, expected", [
    ("AmpC DUDE-Z virtual screening (Unidock)", "AmpC_DUDE-Z_virtual_screening_Unidock"),
    ("DHODH off-target", "DHODH_off-target"),
    ("Mantén el rumbo", "Manten_el_rumbo"),
    ("  spaced  out  ", "spaced_out"),
    ("a/b\\c:d*e?f", "a_b_c_d_e_f"),
    ("drop'quotes\"and`ticks$", "drop_quotes_and_ticks"),
    ("line\nbreak\ttab", "line_break_tab"),
    ("...", "project"),
    ("", "project"),
    ("🧪🧬", "project"),
    ("CON", "project_CON"),  # Windows cannot open a folder of this name
    ("com1.old", "project_com1.old"),
])
def test_a_name_folds_to_something_a_path_parser_can_carry(name, expected):
    assert folder_name(name) == expected


@pytest.mark.parametrize("name", [
    "AmpC DUDE-Z virtual screening (Unidock)", "Mantén el rumbo", "a/b\\c:d*e?f", "x" * 300, "",
])
def test_no_folder_name_holds_what_breaks_a_program_or_a_file_system(name):
    slug = folder_name(name)
    assert slug and len(slug) <= 64
    assert not set(slug) & set(" \t\n'\"`$&|;()<>*?[]!~\\/:")
    assert Path(slug).name == slug  # one path element, never a traversal


def test_two_names_that_fold_alike_get_folders_of_their_own(tmp_path):
    first = folder_for(tmp_path, "A/B run")
    first.mkdir()
    second = folder_for(tmp_path, "A B run")
    assert first.name == "A_B_run" and second.name == "A_B_run_2"
    second.mkdir()
    assert folder_for(tmp_path, "A:B run").name == "A_B_run_3"
