import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
)
from bpy.types import (
    PropertyGroup,
    UIList,
    Operator,
    Panel,
    Menu,
    AddonPreferences
)

# --- Constants ---
TAG_PREFIX = "tag_" # Optional prefix for custom properties to identify them as tags


last_active_object = None

# --- Helper Functions ---

def get_target_objects(context):
    """Gets selected objects. If none, tries to get objects from active collection."""
    # Consider all common object types that can have custom properties and are selectable in 3D view
    relevant_types = {'MESH', 'EMPTY', 'CURVE', 'SURFACE', 'META', 'FONT', 
                      'ARMATURE', 'LATTICE', 'LIGHT', 'CAMERA', 'SPEAKER', 
                      'LIGHT_PROBE', 'GPENCIL'} # Added Grease Pencil and Light Probe
    selected_obs = [obj for obj in context.selected_objects if obj.type in relevant_types]
    if selected_obs:
        return selected_obs
    return []

def get_all_tags_in_file(context):
    """Scans all objects and returns a set of unique tag names."""
    all_tags = set()
    for obj in bpy.data.objects:
        for k in obj.keys():
            # Filter out Blender's internal properties
            if k == "_RNA_UI" or k.startswith("cycles") or k.startswith("cycles_"):
                continue

            is_tag_property = False
            # Check for prefix if TAG_PREFIX is defined
            if TAG_PREFIX:
                if k.startswith(TAG_PREFIX):
                    # Further ensure it's a boolean True, as per our tagging convention
                    if isinstance(obj[k], int) and obj[k] == 1: # Blender booleans are often ints
                        is_tag_property = True
                        all_tags.add(k[len(TAG_PREFIX):])
                    elif isinstance(obj[k], bool) and obj[k] is True:
                        is_tag_property = True
                        all_tags.add(k[len(TAG_PREFIX):])
            else:
                # If no prefix, rely on the convention that the property value is boolean True
                if isinstance(obj[k], int) and obj[k] == 1:
                    is_tag_property = True
                    all_tags.add(k)
                elif isinstance(obj[k], bool) and obj[k] is True:
                    is_tag_property = True
                    all_tags.add(k)
    return sorted(list(all_tags))


def get_tags_on_selected_objects(context):
    """
    Returns a dictionary of tags present on the selected objects.
    Key: tag_name
    Value: 'ALL' if on all selected, 'SOME' if on some.
    Also returns a set of common tags (tags present on ALL selected objects).
    """
    target_objects = get_target_objects(context)
    if not target_objects:
        return {}, set()

    object_tags_list = []
    for obj in target_objects:
        current_obj_tags = set()
        for k in obj.keys():
            tag_name_candidate = None
            is_actual_tag = False

            if TAG_PREFIX:
                if k.startswith(TAG_PREFIX):
                    tag_name_candidate = k[len(TAG_PREFIX):]
                    if (isinstance(obj[k], int) and obj[k] == 1) or \
                       (isinstance(obj[k], bool) and obj[k] is True):
                        is_actual_tag = True
            elif k != "_RNA_UI" and not k.startswith("cycles"): # No prefix, check general custom props
                if (isinstance(obj[k], int) and obj[k] == 1) or \
                   (isinstance(obj[k], bool) and obj[k] is True):
                    tag_name_candidate = k
                    is_actual_tag = True
            
            if is_actual_tag and tag_name_candidate:
                current_obj_tags.add(tag_name_candidate)
        object_tags_list.append(current_obj_tags)

    if not object_tags_list: # Should not happen if target_objects is not empty
        return {}, set()

    # Find all unique tags across selected objects
    all_selected_tags = set.union(*object_tags_list) if object_tags_list else set()
    
    # Find common tags (present on ALL selected objects)
    common_tags = set.intersection(*object_tags_list) if object_tags_list else set()

    tags_status = {}
    for tag in all_selected_tags:
        count = sum(1 for obj_tags in object_tags_list if tag in obj_tags)
        if count == len(target_objects):
            tags_status[tag] = 'ALL'
        elif count > 0: # count < len(target_objects) but > 0
            tags_status[tag] = 'SOME'
            
    return tags_status, common_tags


def add_tag_to_objects(objects, tag_name):
    """Adds a tag (custom property set to True) to a list of objects."""
    if not tag_name:
        return
    # Sanitize tag_name: remove leading/trailing whitespace, replace spaces with underscores
    # Blender custom property names cannot contain spaces.
    sanitized_tag_name = tag_name.strip().replace(" ", "_")
    if not sanitized_tag_name:
        # Handle case where tag_name becomes empty after sanitization
        print(f"Warning: Tag name '{tag_name}' became empty after sanitization. Tag not added.")
        return

    full_tag_name = f"{TAG_PREFIX}{sanitized_tag_name}" if TAG_PREFIX else sanitized_tag_name
    for obj in objects:
        obj[full_tag_name] = True 

def remove_tag_from_objects(objects, tag_name):
    """Removes a tag (custom property) from a list of objects."""
    if not tag_name:
        return
    sanitized_tag_name = tag_name.strip().replace(" ", "_") # Ensure consistency
    if not sanitized_tag_name:
        return

    full_tag_name = f"{TAG_PREFIX}{sanitized_tag_name}" if TAG_PREFIX else sanitized_tag_name
    for obj in objects:
        if full_tag_name in obj:
            del obj[full_tag_name]

def toggle_tag_on_objects(objects, tag_name):
    """Toggles a tag on objects. If any object has it, remove from all. Else, add to all."""
    if not tag_name or not objects:
        return
    
    sanitized_tag_name = tag_name.strip().replace(" ", "_")
    if not sanitized_tag_name:
        print(f"Warning: Tag name '{tag_name}' became empty after sanitization. Tag not toggled.")
        return
        
    full_tag_name = f"{TAG_PREFIX}{sanitized_tag_name}" if TAG_PREFIX else sanitized_tag_name
    
    any_has_tag = any(full_tag_name in obj and ( (isinstance(obj[full_tag_name], int) and obj[full_tag_name] == 1) or \
                                                 (isinstance(obj[full_tag_name], bool) and obj[full_tag_name] is True) )
                       for obj in objects)

    if any_has_tag:
        for obj in objects:
            if full_tag_name in obj:
                del obj[full_tag_name]
    else:
        for obj in objects:
            obj[full_tag_name] = True


# --- Property Groups ---

class TTAGS_ListItem(PropertyGroup):
    """Helper for CollectionProperties used in UILists."""
    name: StringProperty(name="Name", default="Unknown")

class TTAGS_PieMenuItem(PropertyGroup):
    """Represents a tag configured for the Pie Menu."""
    name: StringProperty(name="Tag Name", default="")

class TTAGS_SceneProperties(PropertyGroup):
    """Properties stored per scene for the addon."""
    new_tag_name: StringProperty(
        name="New Tag",
        description="Name for a new tag to be created (spaces will be replaced with underscores)",
        default=""
    )

    selected_object_tags: CollectionProperty(type=TTAGS_ListItem)
    selected_object_tags_index: IntProperty()

    available_tags_in_file: CollectionProperty(type=TTAGS_ListItem)
    available_tags_in_file_index: IntProperty()
    available_tags_filter: StringProperty(
        name="Search Tags",
        description="Filter available tags by name",
        default="",
        update=lambda self, context: TTAGS_OT_UpdateAvailableTagsList.execute_direct(context)
    )
    
    pie_menu_tags: CollectionProperty(type=TTAGS_PieMenuItem)
    active_pie_tag_index: IntProperty(name="Active Pie Tag Index")

    pie_config_available_tags: CollectionProperty(type=TTAGS_ListItem)
    pie_config_available_tags_index: IntProperty()
    pie_config_filter: StringProperty(
        name="Search All Tags",
        description="Filter all tags for pie menu configuration",
        default="",
        update=lambda self, context: TTAGS_OT_UpdatePieConfigAvailableTagsList.execute_direct(context)
    )


# --- Operators ---

class TTAGS_OT_UpdateSelectedObjectTagsList(Operator):
    """Internal operator to refresh the list of tags on selected objects."""
    bl_idname = "ttags.update_selected_tags_list"
    bl_label = "Update Selected Tags List"
    bl_options = {'REGISTER', 'INTERNAL'}

    @staticmethod
    def _update_logic(context):
        """Core logic for updating the selected object tags list."""
        scene_props = context.scene.ttags_props
        scene_props.selected_object_tags.clear()
        tags_status, _ = get_tags_on_selected_objects(context)
        for tag_name, status in sorted(tags_status.items()):
            item = scene_props.selected_object_tags.add()
            item.name = tag_name
        return {'FINISHED'}

    def execute(self, context):
        """Standard operator execution method."""
        return TTAGS_OT_UpdateSelectedObjectTagsList._update_logic(context)

    @classmethod
    def execute_direct(cls, context):
        """Directly calls the update logic, bypassing full operator invocation."""
        cls._update_logic(context)


class TTAGS_OT_UpdateAvailableTagsList(Operator):
    """Internal operator to refresh the list of all available tags in the file."""
    bl_idname = "ttags.update_available_tags_list"
    bl_label = "Update Available Tags List"
    bl_options = {'REGISTER', 'INTERNAL'}

    @staticmethod
    def _update_logic(context):
        """Core logic for updating the available tags list."""
        scene_props = context.scene.ttags_props
        scene_props.available_tags_in_file.clear()
        all_tags = get_all_tags_in_file(context)
        current_filter = scene_props.available_tags_filter.lower()
        for tag_name in all_tags:
            if not current_filter or current_filter in tag_name.lower():
                item = scene_props.available_tags_in_file.add()
                item.name = tag_name
        return {'FINISHED'}

    def execute(self, context):
        """Standard operator execution method."""
        return TTAGS_OT_UpdateAvailableTagsList._update_logic(context)

    @classmethod
    def execute_direct(cls, context):
        """Directly calls the update logic."""
        cls._update_logic(context)

class TTAGS_OT_UpdatePieConfigAvailableTagsList(Operator):
    """Internal operator to refresh the list of all tags for pie config."""
    bl_idname = "ttags.update_pie_config_available_tags"
    bl_label = "Update Pie Config Available Tags"
    bl_options = {'REGISTER', 'INTERNAL'}

    @staticmethod
    def _update_logic(context):
        """Core logic for updating the pie config available tags list."""
        scene_props = context.scene.ttags_props
        scene_props.pie_config_available_tags.clear()
        all_tags = get_all_tags_in_file(context)
        current_filter = scene_props.pie_config_filter.lower()
        for tag_name in all_tags:
            if not current_filter or current_filter in tag_name.lower():
                item = scene_props.pie_config_available_tags.add()
                item.name = tag_name
        return {'FINISHED'}
    
    def execute(self, context):
        """Standard operator execution method."""
        return TTAGS_OT_UpdatePieConfigAvailableTagsList._update_logic(context)

    @classmethod
    def execute_direct(cls, context):
        """Directly calls the update logic."""
        cls._update_logic(context)


class TTAGS_OT_AddTagToSelection(Operator):
    """Creates a new tag and applies it to the current selection."""
    bl_idname = "ttags.add_tag_to_selection"
    bl_label = "Add New Tag"
    bl_description = "Create and apply a new tag to selected objects. Spaces in tag name will be replaced by underscores"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(get_target_objects(context)) and bool(context.scene.ttags_props.new_tag_name.strip())

    def execute(self, context):
        scene_props = context.scene.ttags_props
        new_tag_raw = scene_props.new_tag_name.strip()
        
        if not new_tag_raw:
            self.report({'WARNING'}, "New tag name cannot be empty.")
            return {'CANCELLED'}

        # Sanitize tag name (replace spaces, etc.)
        new_tag_sanitized = new_tag_raw.replace(" ", "_")
        if not new_tag_sanitized: # If tag name was only spaces
            self.report({'WARNING'}, "Tag name cannot consist only of spaces.")
            return {'CANCELLED'}

        target_objects = get_target_objects(context)
        if not target_objects:
            self.report({'WARNING'}, "No suitable objects selected.")
            return {'CANCELLED'}

        add_tag_to_objects(target_objects, new_tag_sanitized) # Use sanitized name
        self.report({'INFO'}, f"Tag '{new_tag_sanitized}' added to {len(target_objects)} object(s).")
        
        TTAGS_OT_UpdateSelectedObjectTagsList.execute_direct(context)
        TTAGS_OT_UpdateAvailableTagsList.execute_direct(context)
        TTAGS_OT_UpdatePieConfigAvailableTagsList.execute_direct(context)
        scene_props.new_tag_name = "" 
        return {'FINISHED'}

class TTAGS_OT_ToggleTagOnSelection(Operator):
    """Toggles a specific tag on the current selection. From UI lists or Pie menu."""
    bl_idname = "ttags.toggle_tag_on_selection"
    bl_label = "Toggle Tag on Selection"
    bl_description = "If any selected has the tag, remove from all. Else, add to all"
    bl_options = {'REGISTER', 'UNDO'}

    tag_name: StringProperty(name="Tag Name")

    @classmethod
    def poll(cls, context):
        return bool(get_target_objects(context)) #and hasattr(cls, "tag_name")

    def execute(self, context):
        target_objects = get_target_objects(context)
        if not target_objects:
            self.report({'WARNING'}, "No suitable objects selected.")
            return {'CANCELLED'}
        if not self.tag_name: # Should be sanitized by caller if needed
            self.report({'WARNING'}, "No tag name provided.")
            return {'CANCELLED'}

        toggle_tag_on_objects(target_objects, self.tag_name)
        
        TTAGS_OT_UpdateSelectedObjectTagsList.execute_direct(context)
        # These might be needed if a tag is completely removed from the scene or newly created by toggle
        TTAGS_OT_UpdateAvailableTagsList.execute_direct(context) 
        TTAGS_OT_UpdatePieConfigAvailableTagsList.execute_direct(context)
        return {'FINISHED'}


class TTAGS_OT_RemoveTagFromSelection(Operator):
    """Removes a specific tag from the current selection."""
    bl_idname = "ttags.remove_tag_from_selection"
    bl_label = "Remove Tag from Selection"
    bl_description = "Remove this tag from all selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    tag_name: StringProperty(name="Tag Name")

    @classmethod
    def poll(cls, context):
        return bool(get_target_objects(context)) #and hasattr(cls, "tag_name")

    def execute(self, context):
        target_objects = get_target_objects(context)
        if not target_objects:
            self.report({'WARNING'}, "No suitable objects selected.")
            return {'CANCELLED'}
        if not self.tag_name: # Should be sanitized by caller
            self.report({'WARNING'}, "No tag name provided.")
            return {'CANCELLED'}

        remove_tag_from_objects(target_objects, self.tag_name)
        self.report({'INFO'}, f"Tag '{self.tag_name}' removed from selection.")
        
        TTAGS_OT_UpdateSelectedObjectTagsList.execute_direct(context)
        TTAGS_OT_UpdateAvailableTagsList.execute_direct(context)
        TTAGS_OT_UpdatePieConfigAvailableTagsList.execute_direct(context)
        return {'FINISHED'}


class TTAGS_OT_SelectByTag(Operator):
    """Selects objects based on a tag."""
    bl_idname = "ttags.select_by_tag"
    bl_label = "Select by Tag"
    bl_description = "Select objects that have the specified tag"
    bl_options = {'REGISTER', 'UNDO'}

    tag_name: StringProperty(name="Tag Name")
    mode: EnumProperty(
        name="Selection Mode",
        items=[
            ('SET', "Set", "Replace current selection"),
            ('ADD', "Add", "Add to current selection"),
            ('SUBTRACT', "Subtract", "Remove from current selection (objects with this tag)"),
            ('FILTER_AND', "Filter (AND)", "Intersect with current selection (keep selected objects that also have this tag)"),
            ('FILTER_NAND', "Filter (NAND)", "From current selection, keep only those that DO NOT have this tag"),
        ],
        default='SET'
    )
    enabled = True

    # @classmethod
    # def poll(cls, context):
    #     return cls.enabled

    def execute(self, context):
        if not self.tag_name:
            self.report({'WARNING'}, "No tag name provided.")
            return {'CANCELLED'}

        # Assume tag_name from UI is already sanitized (e.g. no spaces)
        # If it could have spaces, sanitize it here: self.tag_name.replace(" ", "_")
        full_tag_name = f"{TAG_PREFIX}{self.tag_name}" if TAG_PREFIX else self.tag_name
        
        initial_selection = list(context.selected_objects) 
        
        if self.mode == 'SET':
            bpy.ops.object.select_all(action='DESELECT')
            # After deselecting, initial_selection for filtering purposes becomes empty for 'SET'
            # However, for 'SET', we iterate all objects, so initial_selection isn't used for filtering.
        
        # For modes that modify the current selection, we operate on initial_selection
        # For 'SET' and 'ADD' (when adding new objects not currently selected), we iterate all scene objects

        objects_to_change_selection_state = [] # Tuples of (object, should_be_selected_boolean)

        if self.mode in ('SET', 'ADD'):
            for obj in bpy.data.objects:
                has_tag = full_tag_name in obj and ( (isinstance(obj[full_tag_name], int) and obj[full_tag_name] == 1) or \
                                                     (isinstance(obj[full_tag_name], bool) and obj[full_tag_name] is True) )
                if has_tag:
                    if self.mode == 'SET' or (self.mode == 'ADD' and not obj.select_get()):
                        objects_to_change_selection_state.append((obj, True))
        
        elif self.mode == 'SUBTRACT':
            for obj in initial_selection: # Only consider currently selected objects
                has_tag = full_tag_name in obj and ( (isinstance(obj[full_tag_name], int) and obj[full_tag_name] == 1) or \
                                                     (isinstance(obj[full_tag_name], bool) and obj[full_tag_name] is True) )
                if has_tag:
                    objects_to_change_selection_state.append((obj, False))

        elif self.mode == 'FILTER_AND': # Intersect: keep selected that HAVE the tag
            for obj in initial_selection:
                has_tag = full_tag_name in obj and ( (isinstance(obj[full_tag_name], int) and obj[full_tag_name] == 1) or \
                                                     (isinstance(obj[full_tag_name], bool) and obj[full_tag_name] is True) )
                if not has_tag: # If it's selected but doesn't have the tag
                    objects_to_change_selection_state.append((obj, False))
        
        elif self.mode == 'FILTER_NAND': # Keep selected that DO NOT HAVE the tag
            for obj in initial_selection:
                has_tag = full_tag_name in obj and ( (isinstance(obj[full_tag_name], int) and obj[full_tag_name] == 1) or \
                                                     (isinstance(obj[full_tag_name], bool) and obj[full_tag_name] is True) )
                if has_tag: # If it's selected and has the tag
                    objects_to_change_selection_state.append((obj, False))

        # Apply selection changes
        for obj, select_state in objects_to_change_selection_state:
            obj.select_set(select_state)
            
        if context.selected_objects:
            if context.view_layer.objects.active not in context.selected_objects:
                 context.view_layer.objects.active = context.selected_objects[0]
        else:
            context.view_layer.objects.active = None

        self.report({'INFO'}, f"Selection updated for tag '{self.tag_name}' with mode '{self.mode}'.")
        TTAGS_OT_UpdateSelectedObjectTagsList.execute_direct(context)
        return {'FINISHED'}


class TTAGS_OT_AddTagToPieConfig(Operator):
    """Adds a tag from the 'Available Tags' list to the 'Pie Menu Tags' list."""
    bl_idname = "ttags.add_tag_to_pie_config"
    bl_label = "Add to Pie Menu"
    bl_description = "Add selected available tag to the Pie Menu configuration"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene_props = context.scene.ttags_props
        return scene_props.pie_config_available_tags_index >= 0 and \
               len(scene_props.pie_config_available_tags) > scene_props.pie_config_available_tags_index

    def execute(self, context):
        scene_props = context.scene.ttags_props
        source_list = scene_props.pie_config_available_tags
        source_index = scene_props.pie_config_available_tags_index
        
        if not (0 <= source_index < len(source_list)):
            self.report({'WARNING'}, "No valid tag selected from available list.")
            return {'CANCELLED'}

        tag_to_add = source_list[source_index].name

        if any(pt.name == tag_to_add for pt in scene_props.pie_menu_tags):
            self.report({'INFO'}, f"Tag '{tag_to_add}' is already in the Pie Menu.")
            return {'CANCELLED'}

        if len(scene_props.pie_menu_tags) >= 8:
            self.report({'WARNING'}, "Pie Menu can have a maximum of 8 items.")
            return {'CANCELLED'}

        new_pie_item = scene_props.pie_menu_tags.add()
        new_pie_item.name = tag_to_add
        
        self.report({'INFO'}, f"Tag '{tag_to_add}' added to Pie Menu configuration.")
        return {'FINISHED'}

class TTAGS_OT_RemoveTagFromPieConfig(Operator):
    """Removes the selected tag from the 'Pie Menu Tags' list."""
    bl_idname = "ttags.remove_tag_from_pie_config"
    bl_label = "Remove from Pie Menu"
    bl_description = "Remove selected tag from the Pie Menu configuration"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene_props = context.scene.ttags_props
        return scene_props.active_pie_tag_index >= 0 and \
               len(scene_props.pie_menu_tags) > scene_props.active_pie_tag_index

    def execute(self, context):
        scene_props = context.scene.ttags_props
        target_index = scene_props.active_pie_tag_index
        
        if not (0 <= target_index < len(scene_props.pie_menu_tags)):
            self.report({'WARNING'}, "No valid tag selected from Pie Menu list.")
            return {'CANCELLED'}

        tag_removed = scene_props.pie_menu_tags[target_index].name
        scene_props.pie_menu_tags.remove(target_index)
        
        if scene_props.active_pie_tag_index >= len(scene_props.pie_menu_tags) and len(scene_props.pie_menu_tags) > 0:
            scene_props.active_pie_tag_index = len(scene_props.pie_menu_tags) - 1
        elif not scene_props.pie_menu_tags:
             scene_props.active_pie_tag_index = 0 # Or -1 if appropriate for no selection

        self.report({'INFO'}, f"Tag '{tag_removed}' removed from Pie Menu configuration.")
        return {'FINISHED'}

class TTAGS_OT_MovePieTag(Operator):
    """Moves the selected Pie Menu tag up or down in the list."""
    bl_idname = "ttags.move_pie_tag"
    bl_label = "Move Pie Tag"
    bl_description = "Move selected Pie Menu tag up or down"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(
        name="Direction",
        items=[('UP', "Up", "Move tag up"), ('DOWN', "Down", "Move tag down")],
        default='UP'
    )

    @classmethod
    def poll(cls, context):
        scene_props = context.scene.ttags_props
        idx = scene_props.active_pie_tag_index
        pie_tags_len = len(scene_props.pie_menu_tags)
        
        if not (0 <= idx < pie_tags_len): # Check if index is valid
            return False
        if cls.direction == 'UP' and idx == 0: # Cannot move top item up
            return False
        if cls.direction == 'DOWN' and idx == pie_tags_len - 1: # Cannot move bottom item down
            return False
        return True


    def execute(self, context):
        scene_props = context.scene.ttags_props
        idx = scene_props.active_pie_tag_index
        pie_tags = scene_props.pie_menu_tags

        if self.direction == 'UP':
            if idx > 0:
                pie_tags.move(idx, idx - 1)
                scene_props.active_pie_tag_index -= 1
        elif self.direction == 'DOWN':
            if idx < len(pie_tags) - 1:
                pie_tags.move(idx, idx + 1)
                scene_props.active_pie_tag_index += 1
        
        return {'FINISHED'}


# --- UI Lists ---

class TTAGS_UL_SelectedObjectTagsList(UIList):
    """UIList for displaying tags on the current selection."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        scene_props = context.scene.ttags_props # data is scene_props
        tag_name = item.name # item is TTAGS_ListItem

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            
            tags_status, _ = get_tags_on_selected_objects(context) 
            status_icon = 'NONE' # Default icon
            tag_status_text = ""
            current_tag_status = tags_status.get(tag_name)

            if current_tag_status == 'ALL':
                status_icon = 'CHECKBOX_HLT' # All selected objects have this tag
                tag_status_text = f"{tag_name} (All)"
            elif current_tag_status == 'SOME':
                status_icon = 'PIVOT_BOUNDBOX' # Some selected objects have this tag (partial)
                tag_status_text = f"{tag_name} (Some)"
            else: # Tag not on selection (shouldn't appear here if list is accurate)
                status_icon = 'CHECKBOX_DEHLT' 
                tag_status_text = f"{tag_name} (None)"


            row.label(text=tag_status_text, icon=status_icon)
            
            op_toggle = row.operator(TTAGS_OT_ToggleTagOnSelection.bl_idname, text="", icon='UV_SYNC_SELECT')
            op_toggle.tag_name = tag_name
            
            # Remove button should always remove, not toggle.
            op_remove = row.operator(TTAGS_OT_RemoveTagFromSelection.bl_idname, text="", icon='X')
            op_remove.tag_name = tag_name

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=tag_name, icon_value=icon) # Default icon for grid

class TTAGS_UL_AvailableTagsInFileList(UIList):
    """UIList for displaying all unique tags in the file (for applying/selecting)."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # scene_props = context.scene.ttags_props (data is scene_props)
        tag_name = item.name 

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=tag_name, icon='TAG') 
                    
            # Select buttons container
            select_row = row.row(align=True)
            select_row.scale_x = 0.8 # Make buttons smaller to fit
            
            op_sel_add = select_row.operator(TTAGS_OT_SelectByTag.bl_idname, text="+")
            op_sel_add.tag_name = tag_name
            op_sel_add.mode = 'ADD'

            op_sel_sub = select_row.operator(TTAGS_OT_SelectByTag.bl_idname, text="-")
            op_sel_sub.tag_name = tag_name
            op_sel_sub.mode = 'SUBTRACT'
            

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=tag_name, icon_value=icon) # Default icon for grid
            
    def draw_filter(self, context, layout):
        scene_props = context.scene.ttags_props
        row = layout.row()
        row.prop(scene_props, "available_tags_filter", text="") # Empty text for search field
        # No need for explicit refresh button if update on prop change works well


class TTAGS_UL_PieMenuConfigAvailableTagsList(UIList):
    """UIList for displaying all tags available for Pie Menu configuration."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        tag_name = item.name 
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=tag_name, icon='TAG')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=tag_name, icon_value=icon)

    def draw_filter(self, context, layout):
        scene_props = context.scene.ttags_props
        row = layout.row()
        row.prop(scene_props, "pie_config_filter", text="") # Empty text for search field


class TTAGS_UL_PieMenuTagsList(UIList):
    """UIList for displaying tags configured for the Pie Menu."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        tag_name = item.name
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=tag_name, icon='DOT') 
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=tag_name, icon_value=icon)


# --- Panels ---

class TTAGS_PT_MainPanel(Panel):
    bl_label = "Object Tagger"
    bl_idname = "TTAGS_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tagger' 

    def draw_header(self, context):
        # Optional: Add an icon or a master refresh button to the panel header
        layout = self.layout
        layout.operator(TTAGS_OT_UpdateAllLists.bl_idname, text="", icon='FILE_REFRESH')


    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.ttags_props
        target_objects = get_target_objects(context)

        box = layout.box()
        box.label(text="Create New Tag:")
        row = box.row(align=True)
        row.prop(scene_props, "new_tag_name", text="")
        col = row.column()
        op_add_new = col.operator(TTAGS_OT_AddTagToSelection.bl_idname, text="Add to Selection", icon='ADD')
        col.enabled = bool(target_objects and scene_props.new_tag_name.strip())


        box = layout.box()
        row = box.row(align=True)
        row.label(text="Tags on Current Selection:")
        # Removed individual refresh, relying on header refresh or selection change handler (if implemented)
        # row.operator(TTAGS_OT_UpdateSelectedObjectTagsList.bl_idname, text="", icon='FILE_REFRESH') 

        if target_objects:
            box.template_list(
                "TTAGS_UL_SelectedObjectTagsList", "selected_tags", # Unique ID for this list instance
                scene_props, "selected_object_tags", 
                scene_props, "selected_object_tags_index", 
                rows=max(1, min(len(scene_props.selected_object_tags), 3)), # Dynamic rows
                maxrows=5 
            )
            if not scene_props.selected_object_tags:
                box.label(text="No tags on current selection.")
        else:
            box.label(text="Select object(s) to see their tags.")

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Manage & Select by All Tags:")
        # row.operator(TTAGS_OT_UpdateAvailableTagsList.bl_idname, text="", icon='FILE_REFRESH')
        
        box.prop(scene_props, "available_tags_filter", text="Search", icon='VIEWZOOM')

        box.template_list(
            "TTAGS_UL_AvailableTagsInFileList", "available_tags", # Unique ID
            scene_props, "available_tags_in_file",
            scene_props, "available_tags_in_file_index",
            rows=5, maxrows=10
        )
        # Provide feedback based on filter and available tags
        if not get_all_tags_in_file(context): # Check actual source, not filtered list
             box.label(text="No tags found in the file yet.")
        elif not scene_props.available_tags_in_file and scene_props.available_tags_filter:
             box.label(text="No tags match filter.")
        
        # Select by Tag - Advanced Filter Options (could be a sub-panel or separate operator)
        # For now, keeping it simple with buttons in the list.
        # Could add a dedicated section for more complex selection logic if needed.


        box = layout.box()
        box.label(text="Configure Pie Menu (Max 8 Tags):")
        
        row = box.row(align=True)
        # row.label(text="Available Tags for Pie:") # Label might be redundant due to filter box
        # row.operator(TTAGS_OT_UpdatePieConfigAvailableTagsList.bl_idname, text="", icon='FILE_REFRESH')

        box.prop(scene_props, "pie_config_filter", text="Search All Tags", icon='VIEWZOOM')

        split = box.split(factor=0.2) # Adjusted factor for better balance
        
        col1 = split.column()
        col1.label(text="Available:")
        col1.template_list(
            "TTAGS_UL_PieMenuConfigAvailableTagsList", "pie_available", # Unique ID
            scene_props, "pie_config_available_tags",
            scene_props, "pie_config_available_tags_index",
            rows=5, maxrows=8
        )

        col_mid = split.column(align=True)
        col_mid.separator(factor=0.8) # Add some space

        op_row = col_mid.row()
        op_add_to_pie = op_row.operator(TTAGS_OT_AddTagToPieConfig.bl_idname, text="", icon='TRIA_RIGHT')

        idx_avail = scene_props.pie_config_available_tags_index
        list_avail_len = len(scene_props.pie_config_available_tags)
        op_row.enabled = (0 <= idx_avail < list_avail_len) and (len(scene_props.pie_menu_tags) < 8)
        
        op_row = col_mid.row()
        op_remove_from_pie = op_row.operator(TTAGS_OT_RemoveTagFromPieConfig.bl_idname, text="", icon='TRIA_LEFT')

        #set enabled
        idx_pie = scene_props.active_pie_tag_index
        list_pie_len = len(scene_props.pie_menu_tags)
        op_row.enabled = 0 <= idx_pie < list_pie_len
        
        col_mid.separator(factor=0.2)


        col2 = split.column()
        col2.label(text="In Pie Menu:")
        col2.template_list(
            "TTAGS_UL_PieMenuTagsList", "pie_configured", # Unique ID
            scene_props, "pie_menu_tags",
            scene_props, "active_pie_tag_index",
            rows=5, maxrows=8
        )
        
        sub_row = col2.row(align=True)
        op_move_up = sub_row.operator(TTAGS_OT_MovePieTag.bl_idname, text="", icon='TRIA_UP')
        op_move_up.direction = 'UP'
        op_move_down = sub_row.operator(TTAGS_OT_MovePieTag.bl_idname, text="", icon='TRIA_DOWN')
        op_move_down.direction = 'DOWN'

        # Poll logic for move buttons is handled in TTAGS_OT_MovePieTag.poll
        # op_move_up.enabled = (0 < idx_pie < list_pie_len)
        # op_move_down.enabled = (0 <= idx_pie < list_pie_len - 1)


        if len(scene_props.pie_menu_tags) >= 8 and op_add_to_pie.enabled:
             # This specific check might be redundant if op_add_to_pie.enabled already covers it
            col_mid.label(text="Pie Full!", icon='ERROR') # Or show near the add button

# --- Master Refresh Operator ---
class TTAGS_OT_UpdateAllLists(Operator):
    """Manually refreshes all tag lists in the panel."""
    bl_idname = "ttags.update_all_lists"
    bl_label = "Refresh All Tag Lists"
    bl_description = "Reloads all tag-related lists from the scene data"
    bl_options = {'REGISTER', 'INTERNAL'} # Internal as it's UI-triggered mostly

    def execute(self, context):
        TTAGS_OT_UpdateSelectedObjectTagsList.execute_direct(context)
        TTAGS_OT_UpdateAvailableTagsList.execute_direct(context)
        TTAGS_OT_UpdatePieConfigAvailableTagsList.execute_direct(context)
        # self.report({'INFO'}, "Tag lists refreshed.") # Optional feedback
        return {'FINISHED'}


# --- Pie Menu ---
class TTAGS_MT_ApplyTagPie(Menu):
    bl_label = "Apply/Toggle Tags"
    bl_idname = "TTAGS_MT_apply_tag_pie"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        scene_props = context.scene.ttags_props

        if not scene_props.pie_menu_tags:
            # Provide a more helpful message or direct action
            pie.label(text="No tags configured for Pie Menu.")
            # Could add an operator to open preferences or jump to the panel section
            # pie.operator("screen.userpref_show", text="Open Add-on Preferences") # If settings were in addon prefs
            return

        for i, pie_item in enumerate(scene_props.pie_menu_tags):
            if i >= 8: break 
            op = pie.operator(TTAGS_OT_ToggleTagOnSelection.bl_idname, text=pie_item.name, icon='TAG')
            op.tag_name = pie_item.name


# --- Registration ---
reg_classes = (
    TTAGS_ListItem,
    TTAGS_PieMenuItem,
    TTAGS_SceneProperties,
    TTAGS_OT_UpdateSelectedObjectTagsList,
    TTAGS_OT_UpdateAvailableTagsList,
    TTAGS_OT_UpdatePieConfigAvailableTagsList,
    TTAGS_OT_AddTagToSelection,
    TTAGS_OT_ToggleTagOnSelection,
    TTAGS_OT_RemoveTagFromSelection,
    TTAGS_OT_SelectByTag,
    TTAGS_OT_AddTagToPieConfig,
    TTAGS_OT_RemoveTagFromPieConfig,
    TTAGS_OT_MovePieTag,
    TTAGS_UL_SelectedObjectTagsList,
    TTAGS_UL_AvailableTagsInFileList,
    TTAGS_UL_PieMenuConfigAvailableTagsList,
    TTAGS_UL_PieMenuTagsList,
    TTAGS_PT_MainPanel,
    TTAGS_MT_ApplyTagPie,
    TTAGS_OT_UpdateAllLists, # Register the master refresh operator
)

addon_keymaps = []

# --- Add-on Preferences (Example, not used in current scene_props setup) ---
# class TTAGS_AddonPreferences(AddonPreferences):
#     bl_idname = __name__ # Should be bl_info["name"] or the module name
#     # Define addon preferences here if needed, e.g., for TAG_PREFIX
#     tag_prefix_pref: StringProperty(
#         name="Tag Prefix",
#         description="Optional prefix for custom properties to identify them as tags (e.g., 'tag_'). Leave empty for no prefix.",
#         default="tag_"
#     )
#     def draw(self, context):
#         layout = self.layout
#         layout.prop(self, "tag_prefix_pref")


# --- Scene Update Handler ---
# This handler will try to refresh lists when the selection changes.
# Be cautious with handlers, they can impact performance if not implemented carefully.
# @bpy.app.handlers.depsgraph_update_post
# def ttags_depsgraph_update_post_handler(scene, depsgraph):
#     # Check if the active view layer's selection has changed
#     # This is a common way to detect selection changes, but might not cover all cases
#     # or might trigger too often.
#     # For simplicity, we'll call the update operators.
#     # A more refined approach would check specific depsgraph updates related to selection.
    
#     # This can be too aggressive. Consider if this is truly needed or if manual refresh is better.
#     # If enabling, ensure the operators are efficient.
#     # For now, let's keep it commented out to avoid potential performance issues without more testing.
    
#     # if bpy.context.scene: # Ensure context.scene is available
#     #     try:
#     #         # Check if our properties are available (addon loaded and scene props set up)
#     #         if hasattr(bpy.context.scene, 'ttags_props'):
#     #             # This is a very broad trigger.
#     #             # A better way would be to track previous selection and compare.
#     #             # For now, let's assume it's okay for demonstration.
#     #             TTAGS_OT_UpdateSelectedObjectTagsList.execute_direct(bpy.context)
#     #             # Updating all lists on every depsgraph update is too much.
#     #             # TTAGS_OT_UpdateAvailableTagsList.execute_direct(bpy.context)
#     #             # TTAGS_OT_UpdatePieConfigAvailableTagsList.execute_direct(bpy.context)
#     #     except Exception as e:
#     #         print(f"Error in ttags_depsgraph_update_post_handler: {e}")
#     pass


# This handler updates UI panel in sync with the active object changes.
def msgbus_activelayer_observer(*arg):
    obj = bpy.context.active_object
    if not(last_active_object != obj and obj == obj):
        return
    
    last_active_object = obj

    windows = (w for w in bpy.context.window_manager.windows)
    areas = (area for window in windows for area in window.screen.areas)
    for area in areas:
        if a.type == 'TTAGS_PT_main_panel':
            area.tag_redraw()

owner = object()
def subscribe_message_bus(): 
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.LayerObjects, 'active'),
        owner=owner,
        args=(1,2,3),
        notify=msgbus_activelayer_observer,
        options={'PERSISTENT'}
    )

# Ensure the message bus handler resubs on file changes
@bpy.app.handlers.persistent
def resub_mb_on_loadfile(dummy):
    subscribe_message_bus()


def register():
    # bpy.utils.register_class(TTAGS_AddonPreferences) # If using addon prefs
    for cls in reg_classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.ttags_props = PointerProperty(type=TTAGS_SceneProperties)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(TTAGS_MT_ApplyTagPie.bl_idname, 'V', 'PRESS')
        addon_keymaps.append((km, kmi))
    
    # bpy.app.handlers.depsgraph_update_post.append(ttags_depsgraph_update_post_handler)
    
    subscribe_message_bus()

    if resub_mb_on_loadfile not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(resub_mb_on_loadfile)
    
    # Initial population of lists when addon is enabled
    # Need to ensure a context is available, typically Blender handles this during startup
    # Deferring this to when the panel is first drawn or a manual refresh is safer.


def unregister():
    # bpy.app.handlers.depsgraph_update_post.remove(ttags_depsgraph_update_post_handler)

    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    #del bpy.types.Scene.ttags_props

    if resub_mb_on_loadfile in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(resub_mb_on_loadfile)

    for cls in reversed(reg_classes):
        bpy.utils.unregister_class(cls)
    # bpy.utils.unregister_class(TTAGS_AddonPreferences) # If using addon prefs

