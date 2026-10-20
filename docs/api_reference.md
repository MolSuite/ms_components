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

Off-target scene contexts manage one screen-relative label per grid slot:

```python
dock.set_scene_context(
    "offtarget",
    grid_labels={1: "Complex A", 3: "Complex B"},
)
```

`grid_labels` is also accepted by `PymolControlBar` and `PymolSceneContext`.
Without explicit labels, molecular object titles (or object names when no title
is available) are joined per positive `grid_slot` within the context's `target`.
Applications must pass display names if those names are not present in PyMOL.

Each label is a pseudoatom named `panel_text<slot>`, positioned at the top-left
of its panel with size 14 and PyMOL's background-adaptive `front` color.
Existing labels are updated in place, so individual settings remain editable,
for example `cmd.set("label_size", 18, "panel_text3")`. Presets restore label
visibility after changing molecular representations.

Setting any non-`offtarget` scene context after an off-target context removes
the managed labels and sets `grid_mode` to zero. Applications should update
the scene context when leaving their off-target view, even without loading a
new structure. Unrelated grid scenes and user-created annotations are not
removed.

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
