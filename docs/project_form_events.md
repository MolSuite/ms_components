# Project form events

`ProjectsMenuWidget` and `ProjectBrowserPanel` emit
`project_form_opened(ProjectFormDialog)` before entering a create/edit form's modal
loop. The form's `mode` is `"create"` or `"edit"`. Hosts can bind controls and
observe the normal `accepted`, `rejected`, and `finished` Qt signals without
searching the browser's widget tree or replacing its actions.

`ProjectFormDialog` is exported from `ms_components.ms_projects`. Its public
controls include `name_input`, `path_input`, `path_row`, `browse_button`, and
`save_button`. `name_committed(str)` emits the trimmed name when editing finishes.
`path_selected(str)` emits only when Browse confirms a folder, including selecting
the current folder again. Cancelling the chooser emits no selection event.

`project_created(project_id)` means that project creation succeeded. It remains
separate from opening the form or accepting its fields, which may still be followed
by a backend error. None of these APIs depend on `ms_tutorial` or a host application.
