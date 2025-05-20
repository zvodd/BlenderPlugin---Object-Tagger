bl_info = {
    "name": "Object Tagger",
    "author": "zvodd",
    "version": (1, 1, 4),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar (N Panel) > Tagger Tab | V for Pie Menu",
    "description": "Adds, removes, and manages tags on objects using custom properties. Includes a customizable Pie Menu.",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}
import bpy

# Include *all* modules in this package for proper reloading.
#   * All modules *must* have a register() and unregister() method!
#   * Dependency *must* come *before* modules that use them in the list!
register, unregister = bpy.utils.register_submodule_factory(__package__, (
    'tagger_ui_addon',
))