# API reference

The reference below is generated directly from the current Python sources.
Names beginning with an underscore are implementation details.

## Smart table

::: ms_components.ms_table

## Monitor

::: ms_components.ms_monitor

## Hosts and executors

::: ms_components.ms_executors

## Projects

::: ms_components.ms_projects

## Settings

::: ms_components.ms_settings

## PyMOL

::: ms_components.ms_pymol

Comparison scenes provide grid and overlay layouts without reloading structures
or changing the camera. Assign each structure/pose pair the same positive PyMOL
`grid_slot`, then pass its display name:

```python
dock.set_scene_context(
    "comparison",
    grid_labels={1: "Complex A", 3: "Complex B"},
)
dock.set_comparison_layout("overlay")
```

`grid_labels` is also accepted by `PymolControlBar` and `PymolSceneContext`.
Without explicit labels, molecular object titles (or object names when no title
is available) are joined per positive `grid_slot` within the context's `target`.
Applications must pass display names if those names are not present in PyMOL.

The **Display > Comparison > Grid / Overlay** menu appears only in comparison
scenes. The chosen layout persists when changing poses or applying presets.
Overlay displays the existing coordinates together; alignment remains the
caller's responsibility.

Each label is a pseudoatom named `panel_text<slot>`, initially sized 14.
Grid labels appear at the top-left of their panel; overlay labels form a stacked
legend that follows viewport resizing. Receptor cartoons, carbon atoms and label
text share the slot's `COMPARISON_COLORS` color. Heteroatom colors are preserved.
The label outline uses PyMOL's background-adaptive `front` color for readability
on light and dark backgrounds. The palette has ten colors and repeats beyond ten
slots.
Existing labels are updated in place, so individual settings remain editable,
for example `cmd.set("label_size", 18, "panel_text3")`. Presets restore label
visibility after changing molecular representations.

To replace one pose without rebuilding the scene, pass its bytes directly:

```python
dock.replace_comparison_object(
    "pose_a", pdb_bytes, "pdb",
    reference="receptor_a", label="Complex A [P2]",
)
```

The new object inherits the reference's transformation and slot, is shown as
sticks, and receives the same comparison color. Camera and auto-zoom settings
are preserved. The previous object remains available until the replacement loads
successfully. This API neither fetches data nor calls the hosting application.
Hosts remain responsible for reading their data and discarding stale requests.

Setting any non-comparison scene context after a comparison context removes
the managed labels and sets `grid_mode` to zero. Applications should update
the scene context when leaving their off-target view, even without loading a
new structure. Unrelated grid scenes and user-created annotations are not
removed. `"offtarget"` remains accepted as an alias for `"comparison"`.

## Stepper

::: ms_components.ms_stepper

## Guided tutorials

::: ms_components.ms_tutorial

## Tool panel

::: ms_components.tool_panel

## Step dialog

::: ms_components.step_dialog

## Theme

::: ms_components.theme
