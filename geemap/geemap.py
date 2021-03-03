"""Main module for interactive mapping using Google Earth Engine Python API and ipyleaflet.
Keep in mind that Earth Engine functions use both camel case and snake case, such as setOptions(), setCenter(), centerObject(), addLayer().
ipyleaflet functions use snake case, such as add_tile_layer(), add_wms_layer(), add_minimap().
"""

import math
import os
import time
import ee
import ipyevents
import ipyleaflet
import ipywidgets as widgets
from bqplot import pyplot as plt
from ipyfilechooser import FileChooser
from ipyleaflet import Marker, MarkerCluster, TileLayer, WidgetControl
from IPython.display import display
from .basemaps import basemaps, basemap_tiles
from .common import *
from .legends import builtin_legends


class Map(ipyleaflet.Map):
    """The Map class inherits from ipyleaflet.Map. The arguments you can pass to the Map can be found at https://ipyleaflet.readthedocs.io/en/latest/api_reference/map.html. By default, the Map will add Google Maps as the basemap. Set add_google_map = False to use OpenStreetMap as the basemap.

    Returns:
        object: ipyleaflet map object.
    """

    def __init__(self, **kwargs):

        # Authenticates Earth Engine and initializes an Earth Engine session
        if "ee_initialize" not in kwargs.keys():
            kwargs["ee_initialize"] = True

        if kwargs["ee_initialize"]:
            ee_initialize()

        # Default map center location (lat, lon) and zoom level
        latlon = [40, -100]
        zoom = 4

        # Interchangeable parameters between ipyleaflet and folium
        if "height" not in kwargs.keys():
            kwargs["height"] = "600px"
        if "location" in kwargs.keys():
            kwargs["center"] = kwargs["location"]
            kwargs.pop("location")
        if "center" not in kwargs.keys():
            kwargs["center"] = latlon

        if "zoom_start" in kwargs.keys():
            kwargs["zoom"] = kwargs["zoom_start"]
            kwargs.pop("zoom_start")
        if "zoom" not in kwargs.keys():
            kwargs["zoom"] = zoom

        if "add_google_map" not in kwargs.keys() and "basemap" not in kwargs.keys():
            kwargs["add_google_map"] = True
        if "scroll_wheel_zoom" not in kwargs.keys():
            kwargs["scroll_wheel_zoom"] = True

        if "lite_mode" not in kwargs.keys():
            kwargs["lite_mode"] = False

        if kwargs["lite_mode"]:
            kwargs["data_ctrl"] = False
            kwargs["zoom_ctrl"] = True
            kwargs["fullscreen_ctrl"] = False
            kwargs["draw_ctrl"] = False
            kwargs["search_ctrl"] = False
            kwargs["measure_ctrl"] = False
            kwargs["scale_ctrl"] = False
            kwargs["layer_ctrl"] = False
            kwargs["toolbar_ctrl"] = False
            kwargs["attribution_ctrl"] = False

        if "data_ctrl" not in kwargs.keys():
            kwargs["data_ctrl"] = True
        if "zoom_ctrl" not in kwargs.keys():
            kwargs["zoom_ctrl"] = True
        if "fullscreen_ctrl" not in kwargs.keys():
            kwargs["fullscreen_ctrl"] = True
        if "draw_ctrl" not in kwargs.keys():
            kwargs["draw_ctrl"] = True
        if "search_ctrl" not in kwargs.keys():
            kwargs["search_ctrl"] = False
        if "measure_ctrl" not in kwargs.keys():
            kwargs["measure_ctrl"] = True
        if "scale_ctrl" not in kwargs.keys():
            kwargs["scale_ctrl"] = True
        if "layer_ctrl" not in kwargs.keys():
            kwargs["layer_ctrl"] = False
        if "toolbar_ctrl" not in kwargs.keys():
            kwargs["toolbar_ctrl"] = True
        if "attribution_ctrl" not in kwargs.keys():
            kwargs["attribution_ctrl"] = True
        if "use_voila" not in kwargs.keys():
            kwargs["use_voila"] = False

        if (
            "basemap" in kwargs.keys()
            and isinstance(kwargs["basemap"], str)
            and kwargs["basemap"] in basemaps.keys()
        ):
            kwargs["basemap"] = basemap_tiles[kwargs["basemap"]]

        if os.environ.get("USE_VOILA") is not None:
            kwargs["use_voila"] = True

        # Inherits the ipyleaflet Map class
        super().__init__(**kwargs)
        self.baseclass = "ipyleaflet"
        self.layout.height = kwargs["height"]

        self.clear_controls()

        # The number of shapes drawn by the user using the DrawControl
        self.draw_count = 0
        # The list of Earth Engine Geometry objects converted from geojson
        self.draw_features = []
        # The Earth Engine Geometry object converted from the last drawn feature
        self.draw_last_feature = None
        self.draw_layer = None
        self.draw_last_json = None
        self.draw_last_bounds = None
        self.user_roi = None
        self.user_rois = None

        self.roi_start = False
        self.roi_end = False
        if kwargs["ee_initialize"]:
            self.roi_reducer = ee.Reducer.mean()
        self.roi_reducer_scale = None

        # List for storing pixel values and locations based on user-drawn geometries.
        self.chart_points = []
        self.chart_values = []
        self.chart_labels = None

        self.plot_widget = None  # The plot widget for plotting Earth Engine data
        self.plot_control = None  # The plot control for interacting plotting
        self.random_marker = None

        self.legend_widget = None
        self.legend_control = None
        self.colorbar = None

        self.ee_layers = []
        self.ee_layer_names = []
        self.ee_raster_layers = []
        self.ee_raster_layer_names = []
        self.ee_layer_dict = {}

        self.search_locations = None
        self.search_loc_marker = None
        self.search_loc_geom = None
        self.search_datasets = None
        self.screenshot = None
        self.toolbar = None
        self.toolbar_button = None
        self.vis_control = None
        self.vis_widget = None
        self.colorbar_ctrl = None
        self.colorbar_widget = None
        self.tool_output = None
        self.tool_output_ctrl = None
        self.layer_control = None
        self.convert_ctrl = None

        # Adds search button and search box
        search_button = widgets.ToggleButton(
            value=False,
            tooltip="Search location/data",
            icon="globe",
            layout=widgets.Layout(
                width="28px", height="28px", padding="0px 0px 0px 4px"
            ),
        )

        search_type = widgets.ToggleButtons(
            options=["name/address", "lat-lon", "data"],
            tooltips=[
                "Search by place name or address",
                "Search by lat-lon coordinates",
                "Search Earth Engine data catalog",
            ],
        )
        search_type.style.button_width = "110px"

        search_box = widgets.Text(
            placeholder="Search by place name or address",
            tooltip="Search location",
            layout=widgets.Layout(width="340px"),
        )

        search_output = widgets.Output(
            layout={
                "max_width": "340px",
                "max_height": "250px",
                "overflow": "scroll",
            }
        )

        search_results = widgets.RadioButtons()

        assets_dropdown = widgets.Dropdown(
            options=[],
            layout=widgets.Layout(min_width="279px", max_width="279px"),
        )

        import_btn = widgets.Button(
            description="import",
            button_style="primary",
            tooltip="Click to import the selected asset",
            layout=widgets.Layout(min_width="57px", max_width="57px"),
        )

        def import_btn_clicked(b):
            if assets_dropdown.value != "":
                datasets = self.search_datasets
                dataset = datasets[assets_dropdown.index]
                dataset_uid = "dataset_" + random_string(string_length=3)
                line1 = "{} = {}\n".format(dataset_uid, dataset["ee_id_snippet"])
                line2 = "Map.addLayer(" + dataset_uid + ', {}, "' + dataset["id"] + '")'
                contents = "".join([line1, line2])
                create_code_cell(contents)

        import_btn.on_click(import_btn_clicked)

        html_widget = widgets.HTML()

        def dropdown_change(change):
            dropdown_index = assets_dropdown.index
            if dropdown_index is not None and dropdown_index >= 0:
                with search_output:
                    search_output.clear_output(wait=True)
                    print("Loading ...")
                    datasets = self.search_datasets
                    dataset = datasets[dropdown_index]
                    dataset_html = ee_data_html(dataset)
                    html_widget.value = dataset_html
                    search_output.clear_output(wait=True)
                    display(html_widget)

        assets_dropdown.observe(dropdown_change, names="value")

        assets_combo = widgets.HBox()
        assets_combo.children = [import_btn, assets_dropdown]

        def search_result_change(change):
            result_index = search_results.index
            locations = self.search_locations
            location = locations[result_index]
            latlon = (location.lat, location.lng)
            self.search_loc_geom = ee.Geometry.Point(location.lng, location.lat)
            marker = self.search_loc_marker
            marker.location = latlon
            self.center = latlon

        search_results.observe(search_result_change, names="value")

        def search_btn_click(change):
            if change["new"]:
                search_widget.children = [search_button, search_result_widget]
                search_type.value = "name/address"
            else:
                search_widget.children = [search_button]
                search_result_widget.children = [search_type, search_box]

        search_button.observe(search_btn_click, "value")

        def search_type_changed(change):
            search_box.value = ""
            search_output.clear_output()
            if change["new"] == "name/address":
                search_box.placeholder = "Search by place name or address, e.g., Paris"
                assets_dropdown.options = []
                search_result_widget.children = [
                    search_type,
                    search_box,
                    search_output,
                ]
            elif change["new"] == "lat-lon":
                search_box.placeholder = "Search by lat-lon, e.g., 40, -100"
                assets_dropdown.options = []
                search_result_widget.children = [
                    search_type,
                    search_box,
                    search_output,
                ]
            elif change["new"] == "data":
                search_box.placeholder = (
                    "Search GEE data catalog by keywords, e.g., elevation"
                )
                search_result_widget.children = [
                    search_type,
                    search_box,
                    assets_combo,
                    search_output,
                ]

        search_type.observe(search_type_changed, names="value")

        def search_box_callback(text):

            if text.value != "":
                if search_type.value == "name/address":
                    g = geocode(text.value)
                elif search_type.value == "lat-lon":
                    g = geocode(text.value, reverse=True)
                    if g is None and latlon_from_text(text.value):
                        search_output.clear_output()
                        latlon = latlon_from_text(text.value)
                        self.search_loc_geom = ee.Geometry.Point(latlon[1], latlon[0])
                        if self.search_loc_marker is None:
                            marker = Marker(
                                location=latlon,
                                draggable=False,
                                name="Search location",
                            )
                            self.search_loc_marker = marker
                            self.add_layer(marker)
                            self.center = latlon
                        else:
                            marker = self.search_loc_marker
                            marker.location = latlon
                            self.center = latlon
                        with search_output:
                            print("No address found for {}".format(latlon))
                        return
                elif search_type.value == "data":
                    search_output.clear_output()
                    with search_output:
                        print("Searching ...")
                    self.default_style = {"cursor": "wait"}
                    ee_assets = search_ee_data(text.value)
                    self.search_datasets = ee_assets
                    asset_titles = [x["title"] for x in ee_assets]
                    assets_dropdown.options = asset_titles
                    search_output.clear_output()
                    if len(ee_assets) > 0:
                        html_widget.value = ee_data_html(ee_assets[0])
                    with search_output:
                        display(html_widget)
                    self.default_style = {"cursor": "default"}

                    return

                self.search_locations = g
                if g is not None and len(g) > 0:
                    top_loc = g[0]
                    latlon = (top_loc.lat, top_loc.lng)
                    self.search_loc_geom = ee.Geometry.Point(top_loc.lng, top_loc.lat)
                    if self.search_loc_marker is None:
                        marker = Marker(
                            location=latlon,
                            draggable=False,
                            name="Search location",
                        )
                        self.search_loc_marker = marker
                        self.add_layer(marker)
                        self.center = latlon
                    else:
                        marker = self.search_loc_marker
                        marker.location = latlon
                        self.center = latlon
                    search_results.options = [x.address for x in g]
                    search_result_widget.children = [
                        search_type,
                        search_box,
                        search_output,
                    ]
                    with search_output:
                        search_output.clear_output(wait=True)
                        display(search_results)
                else:
                    with search_output:
                        search_output.clear_output()
                        print("No results could be found.")

        search_box.on_submit(search_box_callback)

        search_result_widget = widgets.VBox([search_type, search_box])
        search_widget = widgets.HBox([search_button])

        search_event = ipyevents.Event(
            source=search_widget, watched_events=["mouseenter", "mouseleave"]
        )

        def handle_search_event(event):

            if event["type"] == "mouseenter":
                search_widget.children = [search_button, search_result_widget]
                # search_type.value = "name/address"
            elif event["type"] == "mouseleave":
                if not search_button.value:
                    search_widget.children = [search_button]
                    search_result_widget.children = [search_type, search_box]

        search_event.on_dom_event(handle_search_event)

        data_control = WidgetControl(widget=search_widget, position="topleft")

        if kwargs.get("data_ctrl"):
            self.add_control(control=data_control)

        search_marker = Marker(
            icon=ipyleaflet.AwesomeIcon(
                name="check", marker_color="green", icon_color="darkgreen"
            )
        )
        search = ipyleaflet.SearchControl(
            position="topleft",
            url="https://nominatim.openstreetmap.org/search?format=json&q={s}",
            zoom=5,
            property_name="display_name",
            marker=search_marker,
        )
        if kwargs.get("search_ctrl"):
            self.add_control(search)

        if kwargs.get("zoom_ctrl"):
            self.add_control(ipyleaflet.ZoomControl(position="topleft"))

        if kwargs.get("layer_ctrl"):
            layer_control = ipyleaflet.LayersControl(position="topright")
            self.layer_control = layer_control
            self.add_control(layer_control)

        if kwargs.get("scale_ctrl"):
            scale = ipyleaflet.ScaleControl(position="bottomleft")
            self.scale_control = scale
            self.add_control(scale)

        if kwargs.get("fullscreen_ctrl"):
            fullscreen = ipyleaflet.FullScreenControl()
            self.fullscreen_control = fullscreen
            self.add_control(fullscreen)

        if kwargs.get("measure_ctrl"):
            measure = ipyleaflet.MeasureControl(
                position="bottomleft",
                active_color="orange",
                primary_length_unit="kilometers",
            )
            self.measure_control = measure
            self.add_control(measure)

        if kwargs.get("add_google_map"):
            self.add_layer(basemap_tiles["ROADMAP"])

        if kwargs.get("attribution_ctrl"):
            self.add_control(ipyleaflet.AttributionControl(position="bottomright"))

        draw_control = ipyleaflet.DrawControl(
            marker={"shapeOptions": {"color": "#3388ff"}},
            rectangle={"shapeOptions": {"color": "#3388ff"}},
            circle={"shapeOptions": {"color": "#3388ff"}},
            circlemarker={},
            edit=True,
            remove=True,
        )

        draw_control_lite = ipyleaflet.DrawControl(
            marker={},
            rectangle={"shapeOptions": {"color": "#3388ff"}},
            circle={"shapeOptions": {"color": "#3388ff"}},
            circlemarker={},
            polyline={},
            polygon={},
            edit=False,
            remove=False,
        )

        # Handles draw events
        def handle_draw(target, action, geo_json):
            try:
                self.roi_start = True
                geom = geojson_to_ee(geo_json, False)
                self.user_roi = geom
                feature = ee.Feature(geom)
                self.draw_last_json = geo_json
                self.draw_last_feature = feature
                if action == "deleted" and len(self.draw_features) > 0:
                    self.draw_features.remove(feature)
                    self.draw_count -= 1
                else:
                    self.draw_features.append(feature)
                    self.draw_count += 1
                collection = ee.FeatureCollection(self.draw_features)
                self.user_rois = collection
                ee_draw_layer = ee_tile_layer(
                    collection, {"color": "blue"}, "Drawn Features", False, 0.5
                )
                draw_layer_index = self.find_layer_index("Drawn Features")

                if draw_layer_index == -1:
                    self.add_layer(ee_draw_layer)
                    self.draw_layer = ee_draw_layer
                else:
                    self.substitute_layer(self.draw_layer, ee_draw_layer)
                    self.draw_layer = ee_draw_layer
                self.roi_end = True
                self.roi_start = False
            except Exception as e:
                self.draw_count = 0
                self.draw_features = []
                self.draw_last_feature = None
                self.draw_layer = None
                self.user_roi = None
                self.roi_start = False
                self.roi_end = False
                print("There was an error creating Earth Engine Feature.")
                raise Exception(e)

        draw_control.on_draw(handle_draw)
        if kwargs.get("draw_ctrl"):
            self.add_control(draw_control)
        self.draw_control = draw_control
        self.draw_control_lite = draw_control_lite

        # Dropdown widget for plotting
        self.plot_dropdown_control = None
        self.plot_dropdown_widget = None
        self.plot_options = {}
        self.plot_marker_cluster = MarkerCluster(name="Marker Cluster")
        self.plot_coordinates = []
        self.plot_markers = []
        self.plot_last_click = []
        self.plot_all_clicks = []
        self.plot_checked = False
        self.inspector_checked = False

        inspector_output = widgets.Output(layout={"border": "1px solid black"})
        inspector_output_control = WidgetControl(
            widget=inspector_output, position="topright"
        )
        tool_output = widgets.Output()
        self.tool_output = tool_output
        tool_output.clear_output(wait=True)
        save_map_widget = widgets.VBox()

        save_type = widgets.ToggleButtons(
            options=["HTML", "PNG", "JPG"],
            tooltips=[
                "Save the map as an HTML file",
                "Take a screenshot and save as a PNG file",
                "Take a screenshot and save as a JPG file",
            ],
        )

        file_chooser = FileChooser(os.getcwd())
        file_chooser.default_filename = "my_map.html"
        file_chooser.use_dir_icons = True

        ok_cancel = widgets.ToggleButtons(
            value=None,
            options=["OK", "Cancel"],
            tooltips=["OK", "Cancel"],
            button_style="primary",
        )

        def save_type_changed(change):
            ok_cancel.value = None
            # file_chooser.reset()
            file_chooser.default_path = os.getcwd()
            if change["new"] == "HTML":
                file_chooser.default_filename = "my_map.html"
            elif change["new"] == "PNG":
                file_chooser.default_filename = "my_map.png"
            elif change["new"] == "JPG":
                file_chooser.default_filename = "my_map.jpg"
            save_map_widget.children = [save_type, file_chooser]

        def chooser_callback(chooser):
            save_map_widget.children = [save_type, file_chooser, ok_cancel]

        def ok_cancel_clicked(change):
            if change["new"] == "OK":
                file_path = file_chooser.selected
                ext = os.path.splitext(file_path)[1]
                if save_type.value == "HTML" and ext.upper() == ".HTML":
                    tool_output.clear_output()
                    self.to_html(file_path)
                elif save_type.value == "PNG" and ext.upper() == ".PNG":
                    tool_output.clear_output()
                    self.toolbar_button.value = False
                    time.sleep(1)
                    screen_capture(outfile=file_path)
                elif save_type.value == "JPG" and ext.upper() == ".JPG":
                    tool_output.clear_output()
                    self.toolbar_button.value = False
                    time.sleep(1)
                    screen_capture(outfile=file_path)
                else:
                    label = widgets.Label(
                        value="The selected file extension does not match the selected exporting type."
                    )
                    save_map_widget.children = [save_type, file_chooser, label]
                self.toolbar_reset()
            elif change["new"] == "Cancel":
                tool_output.clear_output()
                self.toolbar_reset()

        save_type.observe(save_type_changed, names="value")
        ok_cancel.observe(ok_cancel_clicked, names="value")

        file_chooser.register_callback(chooser_callback)

        save_map_widget.children = [save_type, file_chooser]

        tools = {
            "info": {"name": "inspector", "tooltip": "Inspector"},
            "bar-chart": {"name": "plotting", "tooltip": "Plotting"},
            "camera": {
                "name": "to_image",
                "tooltip": "Save map as HTML or image",
            },
            "eraser": {
                "name": "eraser",
                "tooltip": "Remove all drawn features",
            },
            "folder-open": {
                "name": "open_data",
                "tooltip": "Open local vector/raster data",
            },
            # "cloud-download": {
            #     "name": "export_data",
            #     "tooltip": "Export Earth Engine data",
            # },
            "retweet": {
                "name": "convert_js",
                "tooltip": "Convert Earth Engine JavaScript to Python",
            },
            "gears": {
                "name": "whitebox",
                "tooltip": "WhiteboxTools for local geoprocessing",
            },
            # "google": {
            #     "name": "geetoolbox",
            #     "tooltip": "GEE Toolbox for cloud computing",
            # },
            "map": {
                "name": "basemap",
                "tooltip": "Change basemap",
            },
            "hand-o-up": {
                "name": "draw",
                "tooltip": "Collect training samples",
            },
            "question": {
                "name": "help",
                "tooltip": "Get help",
            },
        }

        if kwargs["use_voila"]:
            voila_tools = ["camera", "folder-open", "cloud-download", "gears"]

            for item in voila_tools:
                if item in tools.keys():
                    del tools[item]

        icons = list(tools.keys())
        tooltips = [item["tooltip"] for item in list(tools.values())]

        icon_width = "32px"
        icon_height = "32px"
        n_cols = 2
        n_rows = math.ceil(len(icons) / n_cols)

        toolbar_grid = widgets.GridBox(
            children=[
                widgets.ToggleButton(
                    layout=widgets.Layout(
                        width="auto", height="auto", padding="0px 0px 0px 4px"
                    ),
                    button_style="primary",
                    icon=icons[i],
                    tooltip=tooltips[i],
                )
                for i in range(len(icons))
            ],
            layout=widgets.Layout(
                width="70px",
                grid_template_columns=(icon_width + " ") * 2,
                grid_template_rows=(icon_height + " ") * n_rows,
                grid_gap="1px 1px",
                padding="5px",
            ),
        )
        self.toolbar = toolbar_grid

        def tool_callback(change):

            if change["new"]:
                current_tool = change["owner"]
                for tool in toolbar_grid.children:
                    if tool is not current_tool:
                        tool.value = False
                tool = change["owner"]
                tool_name = tools[tool.icon]["name"]
                if tool_name == "to_image":
                    if tool_output_control not in self.controls:
                        self.add_control(tool_output_control)
                    with tool_output:
                        tool_output.clear_output()
                        display(save_map_widget)
                elif tool_name == "eraser":
                    self.remove_drawn_features()
                    tool.value = False
                elif tool_name == "inspector":
                    self.inspector_checked = tool.value
                    if not self.inspector_checked:
                        inspector_output.clear_output()
                elif tool_name == "plotting":
                    self.plot_checked = True
                    plot_dropdown_widget = widgets.Dropdown(
                        options=list(self.ee_raster_layer_names),
                    )
                    plot_dropdown_widget.layout.width = "18ex"
                    self.plot_dropdown_widget = plot_dropdown_widget
                    plot_dropdown_control = WidgetControl(
                        widget=plot_dropdown_widget, position="topright"
                    )
                    self.plot_dropdown_control = plot_dropdown_control
                    self.add_control(plot_dropdown_control)
                    if self.draw_control in self.controls:
                        self.remove_control(self.draw_control)
                    self.add_control(self.draw_control_lite)
                elif tool_name == "open_data":
                    from .toolbar import open_data_widget

                    open_data_widget(self)
                elif tool_name == "convert_js":
                    from .toolbar import convert_js2py

                    convert_js2py(self)
                elif tool_name == "whitebox":
                    import whiteboxgui.whiteboxgui as wbt

                    tools_dict = wbt.get_wbt_dict()
                    wbt_toolbox = wbt.build_toolbox(
                        tools_dict, max_width="800px", max_height="500px"
                    )
                    wbt_control = WidgetControl(
                        widget=wbt_toolbox, position="bottomright"
                    )
                    self.whitebox = wbt_control
                    self.add_control(wbt_control)
                elif tool_name == "basemap":
                    from .toolbar import change_basemap

                    change_basemap(self)
                elif tool_name == "draw":
                    from .toolbar import collect_samples

                    self.training_ctrl = None
                    collect_samples(self)
                elif tool_name == "help":
                    import webbrowser

                    webbrowser.open_new_tab("https://geemap.org")
                    current_tool.value = False
            else:
                tool = change["owner"]
                tool_name = tools[tool.icon]["name"]
                if tool_name == "to_image":
                    tool_output.clear_output()
                    save_map_widget.children = [save_type, file_chooser]
                    if tool_output_control in self.controls:
                        self.remove_control(tool_output_control)
                if tool_name == "inspector":
                    inspector_output.clear_output()
                    self.inspector_checked = False
                    if inspector_output_control in self.controls:
                        self.remove_control(inspector_output_control)
                elif tool_name == "plotting":
                    self.plot_checked = False
                    plot_dropdown_widget = self.plot_dropdown_widget
                    plot_dropdown_control = self.plot_dropdown_control
                    if plot_dropdown_control in self.controls:
                        self.remove_control(plot_dropdown_control)
                    del plot_dropdown_widget
                    del plot_dropdown_control
                    if self.plot_control in self.controls:
                        plot_control = self.plot_control
                        plot_widget = self.plot_widget
                        self.remove_control(plot_control)
                        self.plot_control = None
                        self.plot_widget = None
                        del plot_control
                        del plot_widget
                    if (
                        self.plot_marker_cluster is not None
                        and self.plot_marker_cluster in self.layers
                    ):
                        self.remove_layer(self.plot_marker_cluster)
                    if self.draw_control_lite in self.controls:
                        self.remove_control(self.draw_control_lite)
                    self.add_control(self.draw_control)
                elif tool_name == "whitebox":
                    if self.whitebox is not None and self.whitebox in self.controls:
                        self.remove_control(self.whitebox)
                elif tool_name == "convert_js":
                    if (
                        self.convert_ctrl is not None
                        and self.convert_ctrl in self.controls
                    ):
                        self.remove_control(self.convert_ctrl)

        for tool in toolbar_grid.children:
            tool.observe(tool_callback, "value")

        toolbar_button = widgets.ToggleButton(
            value=False,
            tooltip="Toolbar",
            icon="wrench",
            layout=widgets.Layout(
                width="28px", height="28px", padding="0px 0px 0px 4px"
            ),
        )
        self.toolbar_button = toolbar_button

        layers_button = widgets.ToggleButton(
            value=False,
            tooltip="Layers",
            icon="server",
            layout=widgets.Layout(height="28px", width="38px"),
        )

        toolbar_widget = widgets.VBox()
        toolbar_widget.children = [toolbar_button]
        toolbar_header = widgets.HBox()
        toolbar_header.children = [layers_button, toolbar_button]
        toolbar_footer = widgets.VBox()
        toolbar_footer.children = [toolbar_grid]

        toolbar_event = ipyevents.Event(
            source=toolbar_widget, watched_events=["mouseenter", "mouseleave"]
        )

        def handle_toolbar_event(event):

            if event["type"] == "mouseenter":
                toolbar_widget.children = [toolbar_header, toolbar_footer]
            elif event["type"] == "mouseleave":
                if not toolbar_button.value:
                    toolbar_widget.children = [toolbar_button]
                    toolbar_button.value = False
                    layers_button.value = False

        toolbar_event.on_dom_event(handle_toolbar_event)

        def toolbar_btn_click(change):
            if change["new"]:
                layers_button.value = False
                toolbar_widget.children = [toolbar_header, toolbar_footer]
            else:
                if not layers_button.value:
                    toolbar_widget.children = [toolbar_button]

        toolbar_button.observe(toolbar_btn_click, "value")

        def layers_btn_click(change):
            if change["new"]:

                layers_hbox = []
                all_layers_chk = widgets.Checkbox(
                    value=False,
                    description="All layers on/off",
                    indent=False,
                    layout=widgets.Layout(height="18px", padding="0px 8px 25px 8px"),
                )
                all_layers_chk.layout.width = "30ex"
                layers_hbox.append(all_layers_chk)

                def all_layers_chk_changed(change):
                    if change["new"]:
                        for layer in self.layers:
                            layer.visible = True
                    else:
                        for layer in self.layers:
                            layer.visible = False

                all_layers_chk.observe(all_layers_chk_changed, "value")

                layers = [
                    lyr
                    for lyr in self.layers[1:]
                    if (
                        isinstance(lyr, TileLayer)
                        or isinstance(lyr, ipyleaflet.WMSLayer)
                    )
                ]

                # if the layers contain unsupported layers (e.g., GeoJSON, GeoData), adds the ipyleaflet built-in LayerControl
                if len(layers) < (len(self.layers) - 1):
                    if self.layer_control is None:
                        layer_control = ipyleaflet.LayersControl(position="topright")
                        self.layer_control = layer_control
                    if self.layer_control not in self.controls:
                        self.add_control(self.layer_control)

                # for non-TileLayer, use layer.style={'opacity':0, 'fillOpacity': 0} to turn layer off.
                for layer in layers:
                    layer_chk = widgets.Checkbox(
                        value=layer.visible,
                        description=layer.name,
                        indent=False,
                        layout=widgets.Layout(height="18px"),
                    )
                    layer_chk.layout.width = "25ex"
                    layer_opacity = widgets.FloatSlider(
                        value=layer.opacity,
                        min=0,
                        max=1,
                        step=0.01,
                        readout=False,
                        layout=widgets.Layout(width="80px"),
                    )
                    layer_settings = widgets.ToggleButton(
                        icon="gear",
                        tooltip=layer.name,
                        layout=widgets.Layout(
                            width="25px", height="25px", padding="0px"
                        ),
                    )

                    def layer_vis_on_click(change):
                        if change["new"]:
                            layer_name = change["owner"].tooltip
                            # if layer_name in self.ee_raster_layer_names:
                            if layer_name in self.ee_layer_names:
                                layer_dict = self.ee_layer_dict[layer_name]

                                if self.vis_widget is not None:
                                    self.vis_widget = None
                                self.vis_widget = self.create_vis_widget(layer_dict)
                                if self.vis_control in self.controls:
                                    self.remove_control(self.vis_control)
                                    self.vis_control = None
                                vis_control = WidgetControl(
                                    widget=self.vis_widget, position="topright"
                                )
                                self.add_control((vis_control))
                                self.vis_control = vis_control
                            else:
                                if self.vis_widget is not None:
                                    self.vis_widget = None
                                if self.vis_control is not None:
                                    if self.vis_control in self.controls:
                                        self.remove_control(self.vis_control)
                                    self.vis_control = None
                            change["owner"].value = False

                    layer_settings.observe(layer_vis_on_click, "value")

                    def layer_chk_changed(change):

                        layer_name = change["owner"].description
                        if layer_name in self.ee_layer_names:
                            if change["new"]:
                                if "legend" in self.ee_layer_dict[layer_name].keys():
                                    legend = self.ee_layer_dict[layer_name]["legend"]
                                    if legend not in self.controls:
                                        self.add_control(legend)
                                if "colorbar" in self.ee_layer_dict[layer_name].keys():
                                    colorbar = self.ee_layer_dict[layer_name][
                                        "colorbar"
                                    ]
                                    if colorbar not in self.controls:
                                        self.add_control(colorbar)
                            else:
                                if "legend" in self.ee_layer_dict[layer_name].keys():
                                    legend = self.ee_layer_dict[layer_name]["legend"]
                                    if legend in self.controls:
                                        self.remove_control(legend)
                                if "colorbar" in self.ee_layer_dict[layer_name].keys():
                                    colorbar = self.ee_layer_dict[layer_name][
                                        "colorbar"
                                    ]
                                    if colorbar in self.controls:
                                        self.remove_control(colorbar)

                    layer_chk.observe(layer_chk_changed, "value")

                    widgets.jslink((layer_chk, "value"), (layer, "visible"))
                    widgets.jsdlink((layer_opacity, "value"), (layer, "opacity"))
                    hbox = widgets.HBox(
                        [layer_chk, layer_settings, layer_opacity],
                        layout=widgets.Layout(padding="0px 8px 0px 8px"),
                    )
                    layers_hbox.append(hbox)

                toolbar_footer.children = layers_hbox
                toolbar_button.value = False
            else:
                toolbar_footer.children = [toolbar_grid]

        layers_button.observe(layers_btn_click, "value")
        toolbar_control = WidgetControl(widget=toolbar_widget, position="topright")

        if kwargs.get("toolbar_ctrl"):
            self.add_control(toolbar_control)

        tool_output_control = WidgetControl(widget=tool_output, position="topright")
        # self.add_control(tool_output_control)

        def handle_interaction(**kwargs):
            latlon = kwargs.get("coordinates")
            if kwargs.get("type") == "click" and self.inspector_checked:
                self.default_style = {"cursor": "wait"}
                if inspector_output_control not in self.controls:
                    self.add_control(inspector_output_control)
                sample_scale = self.getScale()
                layers = self.ee_layers

                with inspector_output:
                    inspector_output.clear_output(wait=True)
                    print(
                        f"Point ({latlon[1]:.4f}, {latlon[0]:.4f}) at {int(self.get_scale())}m/px"
                    )
                    xy = ee.Geometry.Point(latlon[::-1])
                    for index, ee_object in enumerate(layers):
                        layer_names = self.ee_layer_names
                        layer_name = layer_names[index]
                        object_type = ee_object.__class__.__name__

                        if not self.ee_layer_dict[layer_name]["ee_layer"].visible:
                            continue

                        try:
                            if isinstance(ee_object, ee.ImageCollection):
                                ee_object = ee_object.mosaic()
                            elif (
                                isinstance(ee_object, ee.geometry.Geometry)
                                or isinstance(ee_object, ee.feature.Feature)
                                or isinstance(
                                    ee_object,
                                    ee.featurecollection.FeatureCollection,
                                )
                            ):
                                ee_object = ee.FeatureCollection(ee_object)

                            if isinstance(ee_object, ee.Image):
                                item = ee_object.reduceRegion(
                                    ee.Reducer.first(), xy, sample_scale
                                ).getInfo()
                                b_name = "band"
                                if len(item) > 1:
                                    b_name = "bands"
                                print(
                                    "{}: {} ({} {})".format(
                                        layer_name,
                                        object_type,
                                        len(item),
                                        b_name,
                                    )
                                )
                                keys = item.keys()
                                for key in keys:
                                    print("  {}: {}".format(key, item[key]))
                            elif isinstance(ee_object, ee.FeatureCollection):

                                # Check geometry type
                                geom_type = (
                                    ee.Feature(ee_object.first()).geometry().type()
                                )
                                lat, lon = latlon
                                delta = 0.005
                                bbox = ee.Geometry.BBox(
                                    lon - delta,
                                    lat - delta,
                                    lon + delta,
                                    lat + delta,
                                )
                                # Create a bounding box to filter points
                                xy = ee.Algorithms.If(
                                    geom_type.compareTo(ee.String("Point")),
                                    xy,
                                    bbox,
                                )

                                filtered = ee_object.filterBounds(xy)
                                size = filtered.size().getInfo()
                                if size > 0:
                                    first = filtered.first()
                                    props = first.toDictionary().getInfo()
                                    b_name = "property"
                                    if len(props) > 1:
                                        b_name = "properties"
                                    print(
                                        "{}: Feature ({} {})".format(
                                            layer_name, len(props), b_name
                                        )
                                    )
                                    keys = props.keys()
                                    for key in keys:
                                        print("  {}: {}".format(key, props[key]))
                        except Exception as e:
                            print(e)

                self.default_style = {"cursor": "crosshair"}
            if (
                kwargs.get("type") == "click"
                and self.plot_checked
                and len(self.ee_raster_layers) > 0
            ):
                plot_layer_name = self.plot_dropdown_widget.value
                layer_names = self.ee_raster_layer_names
                layers = self.ee_raster_layers
                index = layer_names.index(plot_layer_name)
                ee_object = layers[index]

                if isinstance(ee_object, ee.ImageCollection):
                    ee_object = ee_object.mosaic()

                try:
                    self.default_style = {"cursor": "wait"}
                    plot_options = self.plot_options
                    sample_scale = self.getScale()
                    if "sample_scale" in plot_options.keys() and (
                        plot_options["sample_scale"] is not None
                    ):
                        sample_scale = plot_options["sample_scale"]
                    if "title" not in plot_options.keys():
                        plot_options["title"] = plot_layer_name
                    if ("add_marker_cluster" in plot_options.keys()) and plot_options[
                        "add_marker_cluster"
                    ]:
                        plot_coordinates = self.plot_coordinates
                        markers = self.plot_markers
                        marker_cluster = self.plot_marker_cluster
                        plot_coordinates.append(latlon)
                        self.plot_last_click = latlon
                        self.plot_all_clicks = plot_coordinates
                        markers.append(Marker(location=latlon))
                        marker_cluster.markers = markers
                        self.plot_marker_cluster = marker_cluster

                    band_names = ee_object.bandNames().getInfo()
                    self.chart_labels = band_names

                    if self.roi_end:
                        if self.roi_reducer_scale is None:
                            scale = ee_object.select(0).projection().nominalScale()
                        else:
                            scale = self.roi_reducer_scale
                        dict_values = ee_object.reduceRegion(
                            reducer=self.roi_reducer,
                            geometry=self.user_roi,
                            scale=scale,
                            bestEffort=True,
                        ).getInfo()
                        self.chart_points.append(
                            self.user_roi.centroid(1).coordinates().getInfo()
                        )
                    else:
                        xy = ee.Geometry.Point(latlon[::-1])
                        dict_values = (
                            ee_object.sample(xy, scale=sample_scale)
                            .first()
                            .toDictionary()
                            .getInfo()
                        )
                        self.chart_points.append(xy.coordinates().getInfo())
                    band_values = list(dict_values.values())
                    self.chart_values.append(band_values)
                    self.plot(band_names, band_values, **plot_options)
                    if plot_options["title"] == plot_layer_name:
                        del plot_options["title"]
                    self.default_style = {"cursor": "crosshair"}
                    self.roi_end = False
                except Exception as e:
                    if self.plot_widget is not None:
                        with self.plot_widget:
                            self.plot_widget.clear_output()
                            print("No data for the clicked location.")
                    else:
                        print(e)
                    self.default_style = {"cursor": "crosshair"}
                    self.roi_end = False

        self.on_interaction(handle_interaction)

    def set_options(self, mapTypeId="HYBRID", styles=None, types=None):
        """Adds Google basemap and controls to the ipyleaflet map.

        Args:
            mapTypeId (str, optional): A mapTypeId to set the basemap to. Can be one of "ROADMAP", "SATELLITE", "HYBRID" or "TERRAIN" to select one of the standard Google Maps API map types. Defaults to 'HYBRID'.
            styles (object, optional): A dictionary of custom MapTypeStyle objects keyed with a name that will appear in the map's Map Type Controls. Defaults to None.
            types (list, optional): A list of mapTypeIds to make available. If omitted, but opt_styles is specified, appends all of the style keys to the standard Google Maps API map types.. Defaults to None.
        """
        self.clear_layers()
        self.clear_controls()
        self.scroll_wheel_zoom = True
        self.add_control(ipyleaflet.ZoomControl(position="topleft"))
        self.add_control(ipyleaflet.LayersControl(position="topright"))
        self.add_control(ipyleaflet.ScaleControl(position="bottomleft"))
        self.add_control(ipyleaflet.FullScreenControl())
        self.add_control(ipyleaflet.DrawControl())

        measure = ipyleaflet.MeasureControl(
            position="bottomleft",
            active_color="orange",
            primary_length_unit="kilometers",
        )
        self.add_control(measure)

        try:
            self.add_layer(basemap_tiles[mapTypeId])
        except Exception:
            raise ValueError(
                'Google basemaps can only be one of "ROADMAP", "SATELLITE", "HYBRID" or "TERRAIN".'
            )

    setOptions = set_options

    def add_ee_layer(
        self, ee_object, vis_params={}, name=None, shown=True, opacity=1.0
    ):
        """Adds a given EE object to the map as a layer.

        Args:
            ee_object (Collection|Feature|Image|MapId): The object to add to the map.
            vis_params (dict, optional): The visualization parameters. Defaults to {}.
            name (str, optional): The name of the layer. Defaults to 'Layer N'.
            shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
            opacity (float, optional): The layer's opacity represented as a number between 0 and 1. Defaults to 1.
        """
        from box import Box

        image = None
        if name is None:
            layer_count = len(self.layers)
            name = "Layer " + str(layer_count + 1)

        if (
            not isinstance(ee_object, ee.Image)
            and not isinstance(ee_object, ee.ImageCollection)
            and not isinstance(ee_object, ee.FeatureCollection)
            and not isinstance(ee_object, ee.Feature)
            and not isinstance(ee_object, ee.Geometry)
        ):
            err_str = "\n\nThe image argument in 'addLayer' function must be an instace of one of ee.Image, ee.Geometry, ee.Feature or ee.FeatureCollection."
            raise AttributeError(err_str)

        if (
            isinstance(ee_object, ee.geometry.Geometry)
            or isinstance(ee_object, ee.feature.Feature)
            or isinstance(ee_object, ee.featurecollection.FeatureCollection)
        ):
            features = ee.FeatureCollection(ee_object)

            width = 2

            if "width" in vis_params:
                width = vis_params["width"]

            color = "000000"

            if "color" in vis_params:
                color = vis_params["color"]

            image_fill = features.style(**{"fillColor": color}).updateMask(
                ee.Image.constant(0.5)
            )
            image_outline = features.style(
                **{"color": color, "fillColor": "00000000", "width": width}
            )

            image = image_fill.blend(image_outline)
        elif isinstance(ee_object, ee.image.Image):
            image = ee_object
        elif isinstance(ee_object, ee.imagecollection.ImageCollection):
            image = ee_object.mosaic()

        if "palette" in vis_params and isinstance(vis_params["palette"], Box):
            try:
                vis_params["palette"] = vis_params["palette"]["default"]
            except Exception as e:
                print("The provided palette is invalid.")
                raise Exception(e)

        map_id_dict = ee.Image(image).getMapId(vis_params)
        tile_layer = TileLayer(
            url=map_id_dict["tile_fetcher"].url_format,
            attribution="Google Earth Engine",
            name=name,
            opacity=opacity,
            visible=shown,
        )

        layer = self.find_layer(name=name)
        if layer is not None:

            existing_object = self.ee_layer_dict[name]["ee_object"]

            if isinstance(existing_object, ee.Image) or isinstance(
                existing_object, ee.ImageCollection
            ):
                self.ee_raster_layers.remove(existing_object)
                self.ee_raster_layer_names.remove(name)
                if self.plot_dropdown_widget is not None:
                    self.plot_dropdown_widget.options = list(self.ee_raster_layer_names)

            self.ee_layers.remove(existing_object)
            self.ee_layer_names.remove(name)
            self.remove_layer(layer)

        self.ee_layers.append(ee_object)
        if name not in self.ee_layer_names:
            self.ee_layer_names.append(name)
        self.ee_layer_dict[name] = {
            "ee_object": ee_object,
            "ee_layer": tile_layer,
            "vis_params": vis_params,
        }

        self.add_layer(tile_layer)

        if isinstance(ee_object, ee.Image) or isinstance(ee_object, ee.ImageCollection):
            self.ee_raster_layers.append(ee_object)
            self.ee_raster_layer_names.append(name)
            if self.plot_dropdown_widget is not None:
                self.plot_dropdown_widget.options = list(self.ee_raster_layer_names)

    addLayer = add_ee_layer

    def draw_layer_on_top(self):
        """Move user-drawn feature layer to the top of all layers."""
        draw_layer_index = self.find_layer_index(name="Drawn Features")
        if draw_layer_index > -1 and draw_layer_index < (len(self.layers) - 1):
            layers = list(self.layers)
            layers = (
                layers[0:draw_layer_index]
                + layers[(draw_layer_index + 1) :]
                + [layers[draw_layer_index]]
            )
            self.layers = layers

    def set_center(self, lon, lat, zoom=None):
        """Centers the map view at a given coordinates with the given zoom level.

        Args:
            lon (float): The longitude of the center, in degrees.
            lat (float): The latitude of the center, in degrees.
            zoom (int, optional): The zoom level, from 1 to 24. Defaults to None.
        """
        self.center = (lat, lon)
        if zoom is not None:
            self.zoom = zoom

    setCenter = set_center

    def center_object(self, ee_object, zoom=None):
        """Centers the map view on a given object.

        Args:
            ee_object (Element|Geometry): An Earth Engine object to center on a geometry, image or feature.
            zoom (int, optional): The zoom level, from 1 to 24. Defaults to None.
        """
        if zoom is None and hasattr(self, "fit_bounds"):
            self.zoom_to_object(ee_object)
        else:
            lat = 0
            lon = 0
            if isinstance(ee_object, ee.geometry.Geometry):
                centroid = ee_object.centroid(1)
                lon, lat = centroid.getInfo()["coordinates"]
            else:
                try:
                    centroid = ee_object.geometry().centroid(1)
                    lon, lat = centroid.getInfo()["coordinates"]
                except Exception as e:
                    print(e)
                    raise Exception(e)

            self.setCenter(lon, lat, zoom)

    centerObject = center_object

    def zoom_to_object(self, ee_object):
        """Zoom to the full extent of an Earth Engine object.

        Args:
            ee_object (object): An Earth Engine object, such as Image, ImageCollection, Geometry, Feature, FeatureCollection.

        Raises:
            Exception: Error getting geometry.
        """
        coordinates = None
        if isinstance(ee_object, ee.geometry.Geometry):
            bounds = ee_object.bounds()
            coordinates = bounds.getInfo()["coordinates"][0]

        else:
            try:
                bounds = ee_object.geometry().bounds()
                coordinates = bounds.getInfo()["coordinates"][0]

            except Exception as e:
                print(e)
                raise Exception(e)

        if coordinates is not None:
            south = coordinates[0][1]
            west = coordinates[0][0]
            north = coordinates[2][1]
            east = coordinates[2][0]
            self.fit_bounds([[south, east], [north, west]])

    zoomToObject = zoom_to_object

    def get_scale(self):
        """Returns the approximate pixel scale of the current map view, in meters.

        Returns:
            float: Map resolution in meters.
        """
        zoom_level = self.zoom
        # Reference: https://blogs.bing.com/maps/2006/02/25/map-control-zoom-levels-gt-resolution
        resolution = 156543.04 * math.cos(0) / math.pow(2, zoom_level)
        return resolution

    getScale = get_scale

    def add_basemap(self, basemap="HYBRID"):
        """Adds a basemap to the map.

        Args:
            basemap (str, optional): Can be one of string from ee_basemaps. Defaults to 'HYBRID'.
        """
        try:
            if (
                basemap in basemap_tiles.keys()
                and basemap_tiles[basemap] not in self.layers
            ):
                self.add_layer(basemap_tiles[basemap])

        except Exception:
            raise ValueError(
                "Basemap can only be one of the following:\n  {}".format(
                    "\n  ".join(basemap_tiles.keys())
                )
            )

    def find_layer(self, name):
        """Finds layer by name

        Args:
            name (str): Name of the layer to find.

        Returns:
            object: ipyleaflet layer object.
        """
        layers = self.layers

        for layer in layers:
            if layer.name == name:
                return layer

        return None

    def find_layer_index(self, name):
        """Finds layer index by name

        Args:
            name (str): Name of the layer to find.

        Returns:
            int: Index of the layer with the specified name
        """
        layers = self.layers

        for index, layer in enumerate(layers):
            if layer.name == name:
                return index

        return -1

    def layer_opacity(self, name, value=1.0):
        """Changes layer opacity.

        Args:
            name (str): The name of the layer to change opacity.
            value (float, optional): The opacity value to set. Defaults to 1.0.
        """
        layer = self.find_layer(name)
        try:
            layer.opacity = value
        except Exception as e:
            raise Exception(e)

    def add_wms_layer(
        self,
        url,
        layers,
        name=None,
        attribution="",
        format="image/jpeg",
        transparent=False,
        opacity=1.0,
        shown=True,
        **kwargs,
    ):
        """Add a WMS layer to the map.

        Args:
            url (str): The URL of the WMS web service.
            layers (str): Comma-separated list of WMS layers to show.
            name (str, optional): The layer name to use on the layer control. Defaults to None.
            attribution (str, optional): The attribution of the data layer. Defaults to ''.
            format (str, optional): WMS image format (use ‘image/png’ for layers with transparency). Defaults to 'image/jpeg'.
            transparent (bool, optional): If True, the WMS service will return images with transparency. Defaults to False.
            opacity (float, optional): The opacity of the layer. Defaults to 1.0.
            shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
        """

        if name is None:
            name = str(layers)

        try:
            wms_layer = ipyleaflet.WMSLayer(
                url=url,
                layers=layers,
                name=name,
                attribution=attribution,
                format=format,
                transparent=transparent,
                opacity=opacity,
                visible=shown,
                **kwargs,
            )
            self.add_layer(wms_layer)

        except Exception as e:
            print("Failed to add the specified WMS TileLayer.")
            raise Exception(e)

    def add_tile_layer(
        self,
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        name="Untitled",
        attribution="",
        opacity=1.0,
        shown=True,
        **kwargs,
    ):
        """Adds a TileLayer to the map.

        Args:
            url (str, optional): The URL of the tile layer. Defaults to 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'.
            name (str, optional): The layer name to use for the layer. Defaults to 'Untitled'.
            attribution (str, optional): The attribution to use. Defaults to ''.
            opacity (float, optional): The opacity of the layer. Defaults to 1.
            shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
        """
        try:
            tile_layer = TileLayer(
                url=url,
                name=name,
                attribution=attribution,
                opacity=opacity,
                visible=shown,
                **kwargs,
            )
            self.add_layer(tile_layer)

        except Exception as e:
            print("Failed to add the specified TileLayer.")
            raise Exception(e)

    def add_COG_layer(
        self,
        url,
        name="Untitled",
        attribution="",
        opacity=1.0,
        shown=True,
        titiler_endpoint="https://api.cogeo.xyz/",
        **kwargs,
    ):
        """Adds a COG TileLayer to the map.

        Args:
            url (str): The URL of the COG tile layer.
            name (str, optional): The layer name to use for the layer. Defaults to 'Untitled'.
            attribution (str, optional): The attribution to use. Defaults to ''.
            opacity (float, optional): The opacity of the layer. Defaults to 1.
            shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
            titiler_endpoint (str, optional): Titiler endpoint. Defaults to "https://api.cogeo.xyz/".
        """
        tile_url = get_COG_tile(url, titiler_endpoint, **kwargs)
        center = get_COG_center(url, titiler_endpoint)  # (lon, lat)
        self.add_tile_layer(tile_url, name, attribution, opacity, shown)
        self.set_center(lon=center[0], lat=center[1], zoom=10)

    def add_COG_mosaic(
        self,
        links,
        name="Untitled",
        attribution="",
        opacity=1.0,
        shown=True,
        titiler_endpoint="https://api.cogeo.xyz/",
        username="anonymous",
        overwrite=False,
        show_footprints=False,
        verbose=True,
        **kwargs,
    ):
        """Add a virtual mosaic of COGs to the map.

        Args:
            links (list): A list of links pointing to COGs.
            name (str, optional): The layer name to use for the layer. Defaults to 'Untitled'.
            attribution (str, optional): The attribution to use. Defaults to ''.
            opacity (float, optional): The opacity of the layer. Defaults to 1.
            shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
            titiler_endpoint (str, optional): Titiler endpoint. Defaults to "https://api.cogeo.xyz/".
            username (str, optional): The username to create mosaic using the titiler endpoint. Defaults to 'anonymous'.
            overwrite (bool, optional): Whether or not to replace existing layer with the same layer name. Defaults to False.
            show_footprints (bool, optional): Whether or not to show footprints of COGs. Defaults to False.
            verbose (bool, optional): Whether or not to print descriptions. Defaults to True.
        """
        layername = name.replace(" ", "_")
        tile = get_COG_mosaic(
            links,
            titiler_endpoint=titiler_endpoint,
            username=username,
            layername=layername,
            overwrite=overwrite,
            verbose=verbose,
        )
        self.add_tile_layer(tile, name, attribution, opacity, shown)

        if show_footprints:
            if verbose:
                print(
                    f"Generating footprints of {len(links)} COGs. This might take a while ..."
                )
            coords = []
            for link in links:
                coord = get_COG_bounds(link)
                if coord is not None:
                    coords.append(coord)
            fc = coords_to_geojson(coords)

            geo_json = ipyleaflet.GeoJSON(
                data=fc,
                style={
                    "opacity": 1,
                    "dashArray": "1",
                    "fillOpacity": 0,
                    "weight": 1,
                },
                name="Footprints",
            )

            self.add_layer(geo_json)
            center = get_center(fc)
            if verbose:
                print("The footprint layer has been added.")
        else:
            center = get_COG_center(links[0], titiler_endpoint)

        self.set_center(center[0], center[1], zoom=6)

    def add_STAC_layer(
        self,
        url,
        bands=None,
        name="Untitled",
        attribution="",
        opacity=1.0,
        shown=True,
        titiler_endpoint="https://api.cogeo.xyz/",
        **kwargs,
    ):
        """Adds a STAC TileLayer to the map.

        Args:
            url (str): The URL of the COG tile layer.
            name (str, optional): The layer name to use for the layer. Defaults to 'Untitled'.
            attribution (str, optional): The attribution to use. Defaults to ''.
            opacity (float, optional): The opacity of the layer. Defaults to 1.
            shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
            titiler_endpoint (str, optional): Titiler endpoint. Defaults to "https://api.cogeo.xyz/".
        """
        tile_url = get_STAC_tile(url, bands, titiler_endpoint, **kwargs)
        center = get_STAC_center(url, titiler_endpoint)
        self.add_tile_layer(tile_url, name, attribution, opacity, shown)
        self.set_center(lon=center[0], lat=center[1], zoom=10)

    def add_minimap(self, zoom=5, position="bottomright"):
        """Adds a minimap (overview) to the ipyleaflet map.

        Args:
            zoom (int, optional): Initial map zoom level. Defaults to 5.
            position (str, optional): Position of the minimap. Defaults to "bottomright".
        """
        minimap = ipyleaflet.Map(
            zoom_control=False,
            attribution_control=False,
            zoom=zoom,
            center=self.center,
            layers=[basemap_tiles["ROADMAP"]],
        )
        minimap.layout.width = "150px"
        minimap.layout.height = "150px"
        ipyleaflet.link((minimap, "center"), (self, "center"))
        minimap_control = WidgetControl(widget=minimap, position=position)
        self.add_control(minimap_control)

    def marker_cluster(self):
        """Adds a marker cluster to the map and returns a list of ee.Feature, which can be accessed using Map.ee_marker_cluster.

        Returns:
            object: a list of ee.Feature
        """
        coordinates = []
        markers = []
        marker_cluster = MarkerCluster(name="Marker Cluster")
        self.last_click = []
        self.all_clicks = []
        self.ee_markers = []
        self.add_layer(marker_cluster)

        def handle_interaction(**kwargs):
            latlon = kwargs.get("coordinates")
            if kwargs.get("type") == "click":
                coordinates.append(latlon)
                geom = ee.Geometry.Point(latlon[1], latlon[0])
                feature = ee.Feature(geom)
                self.ee_markers.append(feature)
                self.last_click = latlon
                self.all_clicks = coordinates
                markers.append(Marker(location=latlon))
                marker_cluster.markers = markers
            elif kwargs.get("type") == "mousemove":
                pass

        # cursor style: https://www.w3schools.com/cssref/pr_class_cursor.asp
        self.default_style = {"cursor": "crosshair"}
        self.on_interaction(handle_interaction)

    def set_plot_options(
        self,
        add_marker_cluster=False,
        sample_scale=None,
        plot_type=None,
        overlay=False,
        position="bottomright",
        min_width=None,
        max_width=None,
        min_height=None,
        max_height=None,
        **kwargs,
    ):
        """Sets plotting options.

        Args:
            add_marker_cluster (bool, optional): Whether to add a marker cluster. Defaults to False.
            sample_scale (float, optional):  A nominal scale in meters of the projection to sample in . Defaults to None.
            plot_type (str, optional): The plot type can be one of "None", "bar", "scatter" or "hist". Defaults to None.
            overlay (bool, optional): Whether to overlay plotted lines on the figure. Defaults to False.
            position (str, optional): Position of the control, can be ‘bottomleft’, ‘bottomright’, ‘topleft’, or ‘topright’. Defaults to 'bottomright'.
            min_width (int, optional): Min width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_width (int, optional): Max width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            min_height (int, optional): Min height of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_height (int, optional): Max height of the widget (in pixels), if None it will respect the content size. Defaults to None.

        """
        plot_options_dict = {}
        plot_options_dict["add_marker_cluster"] = add_marker_cluster
        plot_options_dict["sample_scale"] = sample_scale
        plot_options_dict["plot_type"] = plot_type
        plot_options_dict["overlay"] = overlay
        plot_options_dict["position"] = position
        plot_options_dict["min_width"] = min_width
        plot_options_dict["max_width"] = max_width
        plot_options_dict["min_height"] = min_height
        plot_options_dict["max_height"] = max_height

        for key in kwargs.keys():
            plot_options_dict[key] = kwargs[key]

        self.plot_options = plot_options_dict

        if add_marker_cluster and (self.plot_marker_cluster not in self.layers):
            self.add_layer(self.plot_marker_cluster)

    def plot(
        self,
        x,
        y,
        plot_type=None,
        overlay=False,
        position="bottomright",
        min_width=None,
        max_width=None,
        min_height=None,
        max_height=None,
        **kwargs,
    ):
        """Creates a plot based on x-array and y-array data.

        Args:
            x (numpy.ndarray or list): The x-coordinates of the plotted line.
            y (numpy.ndarray or list): The y-coordinates of the plotted line.
            plot_type (str, optional): The plot type can be one of "None", "bar", "scatter" or "hist". Defaults to None.
            overlay (bool, optional): Whether to overlay plotted lines on the figure. Defaults to False.
            position (str, optional): Position of the control, can be ‘bottomleft’, ‘bottomright’, ‘topleft’, or ‘topright’. Defaults to 'bottomright'.
            min_width (int, optional): Min width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_width (int, optional): Max width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            min_height (int, optional): Min height of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_height (int, optional): Max height of the widget (in pixels), if None it will respect the content size. Defaults to None.

        """
        if self.plot_widget is not None:
            plot_widget = self.plot_widget
        else:
            plot_widget = widgets.Output(layout={"border": "1px solid black"})
            plot_control = WidgetControl(
                widget=plot_widget,
                position=position,
                min_width=min_width,
                max_width=max_width,
                min_height=min_height,
                max_height=max_height,
            )
            self.plot_widget = plot_widget
            self.plot_control = plot_control
            self.add_control(plot_control)

        if max_width is None:
            max_width = 500
        if max_height is None:
            max_height = 300

        if (plot_type is None) and ("markers" not in kwargs.keys()):
            kwargs["markers"] = "circle"

        with plot_widget:
            try:
                fig = plt.figure(1, **kwargs)
                if max_width is not None:
                    fig.layout.width = str(max_width) + "px"
                if max_height is not None:
                    fig.layout.height = str(max_height) + "px"

                plot_widget.clear_output(wait=True)
                if not overlay:
                    plt.clear()

                if plot_type is None:
                    if "marker" not in kwargs.keys():
                        kwargs["marker"] = "circle"
                    plt.plot(x, y, **kwargs)
                elif plot_type == "bar":
                    plt.bar(x, y, **kwargs)
                elif plot_type == "scatter":
                    plt.scatter(x, y, **kwargs)
                elif plot_type == "hist":
                    plt.hist(y, **kwargs)
                plt.show()

            except Exception as e:
                print("Failed to create plot.")
                raise Exception(e)

    def plot_demo(
        self,
        iterations=20,
        plot_type=None,
        overlay=False,
        position="bottomright",
        min_width=None,
        max_width=None,
        min_height=None,
        max_height=None,
        **kwargs,
    ):
        """A demo of interactive plotting using random pixel coordinates.

        Args:
            iterations (int, optional): How many iterations to run for the demo. Defaults to 20.
            plot_type (str, optional): The plot type can be one of "None", "bar", "scatter" or "hist". Defaults to None.
            overlay (bool, optional): Whether to overlay plotted lines on the figure. Defaults to False.
            position (str, optional): Position of the control, can be ‘bottomleft’, ‘bottomright’, ‘topleft’, or ‘topright’. Defaults to 'bottomright'.
            min_width (int, optional): Min width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_width (int, optional): Max width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            min_height (int, optional): Min height of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_height (int, optional): Max height of the widget (in pixels), if None it will respect the content size. Defaults to None.
        """

        import numpy as np
        import time

        if self.random_marker is not None:
            self.remove_layer(self.random_marker)

        image = ee.Image("LE7_TOA_5YEAR/1999_2003").select([0, 1, 2, 3, 4, 6])
        self.addLayer(
            image,
            {"bands": ["B4", "B3", "B2"], "gamma": 1.4},
            "LE7_TOA_5YEAR/1999_2003",
        )
        self.setCenter(-50.078877, 25.190030, 3)
        band_names = image.bandNames().getInfo()
        # band_count = len(band_names)

        latitudes = np.random.uniform(30, 48, size=iterations)
        longitudes = np.random.uniform(-121, -76, size=iterations)

        marker = Marker(location=(0, 0))
        self.random_marker = marker
        self.add_layer(marker)

        for i in range(iterations):
            try:
                coordinate = ee.Geometry.Point([longitudes[i], latitudes[i]])
                dict_values = image.sample(coordinate).first().toDictionary().getInfo()
                band_values = list(dict_values.values())
                title = "{}/{}: Spectral signature at ({}, {})".format(
                    i + 1,
                    iterations,
                    round(latitudes[i], 2),
                    round(longitudes[i], 2),
                )
                marker.location = (latitudes[i], longitudes[i])
                self.plot(
                    band_names,
                    band_values,
                    plot_type=plot_type,
                    overlay=overlay,
                    min_width=min_width,
                    max_width=max_width,
                    min_height=min_height,
                    max_height=max_height,
                    title=title,
                    **kwargs,
                )
                time.sleep(0.3)
            except Exception as e:
                raise Exception(e)

    def plot_raster(
        self,
        ee_object=None,
        sample_scale=None,
        plot_type=None,
        overlay=False,
        position="bottomright",
        min_width=None,
        max_width=None,
        min_height=None,
        max_height=None,
        **kwargs,
    ):
        """Interactive plotting of Earth Engine data by clicking on the map.

        Args:
            ee_object (object, optional): The ee.Image or ee.ImageCollection to sample. Defaults to None.
            sample_scale (float, optional): A nominal scale in meters of the projection to sample in. Defaults to None.
            plot_type (str, optional): The plot type can be one of "None", "bar", "scatter" or "hist". Defaults to None.
            overlay (bool, optional): Whether to overlay plotted lines on the figure. Defaults to False.
            position (str, optional): Position of the control, can be ‘bottomleft’, ‘bottomright’, ‘topleft’, or ‘topright’. Defaults to 'bottomright'.
            min_width (int, optional): Min width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_width (int, optional): Max width of the widget (in pixels), if None it will respect the content size. Defaults to None.
            min_height (int, optional): Min height of the widget (in pixels), if None it will respect the content size. Defaults to None.
            max_height (int, optional): Max height of the widget (in pixels), if None it will respect the content size. Defaults to None.

        """
        if self.plot_control is not None:
            del self.plot_widget
            if self.plot_control in self.controls:
                self.remove_control(self.plot_control)

        if self.random_marker is not None:
            self.remove_layer(self.random_marker)

        plot_widget = widgets.Output(layout={"border": "1px solid black"})
        plot_control = WidgetControl(
            widget=plot_widget,
            position=position,
            min_width=min_width,
            max_width=max_width,
            min_height=min_height,
            max_height=max_height,
        )
        self.plot_widget = plot_widget
        self.plot_control = plot_control
        self.add_control(plot_control)

        self.default_style = {"cursor": "crosshair"}
        msg = "The plot function can only be used on ee.Image or ee.ImageCollection with more than one band."
        if (ee_object is None) and len(self.ee_raster_layers) > 0:
            ee_object = self.ee_raster_layers[-1]
            if isinstance(ee_object, ee.ImageCollection):
                ee_object = ee_object.mosaic()
        elif isinstance(ee_object, ee.ImageCollection):
            ee_object = ee_object.mosaic()
        elif not isinstance(ee_object, ee.Image):
            print(msg)
            return

        if sample_scale is None:
            sample_scale = self.getScale()

        if max_width is None:
            max_width = 500

        band_names = ee_object.bandNames().getInfo()

        coordinates = []
        markers = []
        marker_cluster = MarkerCluster(name="Marker Cluster")
        self.last_click = []
        self.all_clicks = []
        self.add_layer(marker_cluster)

        def handle_interaction(**kwargs2):
            latlon = kwargs2.get("coordinates")

            if kwargs2.get("type") == "click":
                try:
                    coordinates.append(latlon)
                    self.last_click = latlon
                    self.all_clicks = coordinates
                    markers.append(Marker(location=latlon))
                    marker_cluster.markers = markers
                    self.default_style = {"cursor": "wait"}
                    xy = ee.Geometry.Point(latlon[::-1])
                    dict_values = (
                        ee_object.sample(xy, scale=sample_scale)
                        .first()
                        .toDictionary()
                        .getInfo()
                    )
                    band_values = list(dict_values.values())
                    self.plot(
                        band_names,
                        band_values,
                        plot_type=plot_type,
                        overlay=overlay,
                        min_width=min_width,
                        max_width=max_width,
                        min_height=min_height,
                        max_height=max_height,
                        **kwargs,
                    )
                    self.default_style = {"cursor": "crosshair"}
                except Exception as e:
                    if self.plot_widget is not None:
                        with self.plot_widget:
                            self.plot_widget.clear_output()
                            print("No data for the clicked location.")
                    else:
                        print(e)
                    self.default_style = {"cursor": "crosshair"}

        self.on_interaction(handle_interaction)

    def add_maker_cluster(self, event="click", add_marker=True):
        """Captures user inputs and add markers to the map.

        Args:
            event (str, optional): [description]. Defaults to 'click'.
            add_marker (bool, optional): If True, add markers to the map. Defaults to True.

        Returns:
            object: a marker cluster.
        """
        coordinates = []
        markers = []
        marker_cluster = MarkerCluster(name="Marker Cluster")
        self.last_click = []
        self.all_clicks = []
        if add_marker:
            self.add_layer(marker_cluster)

        def handle_interaction(**kwargs):
            latlon = kwargs.get("coordinates")

            if event == "click" and kwargs.get("type") == "click":
                coordinates.append(latlon)
                self.last_click = latlon
                self.all_clicks = coordinates
                if add_marker:
                    markers.append(Marker(location=latlon))
                    marker_cluster.markers = markers
            elif kwargs.get("type") == "mousemove":
                pass

        # cursor style: https://www.w3schools.com/cssref/pr_class_cursor.asp
        self.default_style = {"cursor": "crosshair"}
        self.on_interaction(handle_interaction)

    def set_control_visibility(
        self, layerControl=True, fullscreenControl=True, latLngPopup=True
    ):
        """Sets the visibility of the controls on the map.

        Args:
            layerControl (bool, optional): Whether to show the control that allows the user to toggle layers on/off. Defaults to True.
            fullscreenControl (bool, optional): Whether to show the control that allows the user to make the map full-screen. Defaults to True.
            latLngPopup (bool, optional): Whether to show the control that pops up the Lat/lon when the user clicks on the map. Defaults to True.
        """
        pass

    setControlVisibility = set_control_visibility

    def add_layer_control(self):
        """Adds the layer control to the map."""
        pass

    addLayerControl = add_layer_control

    def split_map(self, left_layer="HYBRID", right_layer="ESRI"):
        """Adds split map.

        Args:
            left_layer (str, optional): The layer tile layer. Defaults to 'HYBRID'.
            right_layer (str, optional): The right tile layer. Defaults to 'ESRI'.
        """
        try:
            if left_layer in basemap_tiles.keys():
                left_layer = basemap_tiles[left_layer]

            if right_layer in basemap_tiles.keys():
                right_layer = basemap_tiles[right_layer]

            control = ipyleaflet.SplitMapControl(
                left_layer=left_layer, right_layer=right_layer
            )
            self.add_control(control)

        except Exception as e:
            print("The provided layers are invalid!")
            raise ValueError(e)

    def ts_inspector(
        self,
        left_ts,
        right_ts,
        left_names,
        right_names,
        left_vis={},
        right_vis={},
    ):
        """Creates a split-panel map for inspecting timeseries images.

        Args:
            left_ts (object): An ee.ImageCollection to show on the left panel.
            right_ts (object): An ee.ImageCollection to show on the right panel.
            left_names (list): A list of names to show under the left dropdown.
            right_names (list): A list of names to show under the right dropdown.
            left_vis (dict, optional): Visualization parameters for the left layer. Defaults to {}.
            right_vis (dict, optional): Visualization parameters for the right layer. Defaults to {}.
        """
        left_count = int(left_ts.size().getInfo())
        right_count = int(right_ts.size().getInfo())

        if left_count != len(left_names):
            print(
                "The number of images in left_ts must match the number of layer names in left_names."
            )
            return
        if right_count != len(right_names):
            print(
                "The number of images in right_ts must match the number of layer names in right_names."
            )
            return

        left_layer = TileLayer(
            url="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
            attribution="Google",
            name="Google Maps",
        )
        right_layer = TileLayer(
            url="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
            attribution="Google",
            name="Google Maps",
        )

        self.clear_controls()
        left_dropdown = widgets.Dropdown(options=left_names, value=None)
        right_dropdown = widgets.Dropdown(options=right_names, value=None)
        left_dropdown.layout.max_width = "130px"
        right_dropdown.layout.max_width = "130px"

        left_control = WidgetControl(widget=left_dropdown, position="topleft")
        right_control = WidgetControl(widget=right_dropdown, position="topright")

        self.add_control(control=left_control)
        self.add_control(control=right_control)

        self.add_control(ipyleaflet.ZoomControl(position="topleft"))
        self.add_control(ipyleaflet.ScaleControl(position="bottomleft"))
        self.add_control(ipyleaflet.FullScreenControl())

        def left_dropdown_change(change):
            left_dropdown_index = left_dropdown.index
            if left_dropdown_index is not None and left_dropdown_index >= 0:
                try:
                    if isinstance(left_ts, ee.ImageCollection):
                        left_image = left_ts.toList(left_ts.size()).get(
                            left_dropdown_index
                        )
                    elif isinstance(left_ts, ee.List):
                        left_image = left_ts.get(left_dropdown_index)
                    else:
                        print("The left_ts argument must be an ImageCollection.")
                        return

                    if isinstance(left_image, ee.ImageCollection):
                        left_image = ee.Image(left_image.mosaic())
                    elif isinstance(left_image, ee.Image):
                        pass
                    else:
                        left_image = ee.Image(left_image)

                    left_image = ee_tile_layer(
                        left_image, left_vis, left_names[left_dropdown_index]
                    )
                    left_layer.url = left_image.url
                except Exception as e:
                    print(e)
                    return

        left_dropdown.observe(left_dropdown_change, names="value")

        def right_dropdown_change(change):
            right_dropdown_index = right_dropdown.index
            if right_dropdown_index is not None and right_dropdown_index >= 0:
                try:
                    if isinstance(right_ts, ee.ImageCollection):
                        right_image = right_ts.toList(left_ts.size()).get(
                            right_dropdown_index
                        )
                    elif isinstance(right_ts, ee.List):
                        right_image = right_ts.get(right_dropdown_index)
                    else:
                        print("The left_ts argument must be an ImageCollection.")
                        return

                    if isinstance(right_image, ee.ImageCollection):
                        right_image = ee.Image(right_image.mosaic())
                    elif isinstance(right_image, ee.Image):
                        pass
                    else:
                        right_image = ee.Image(right_image)

                    right_image = ee_tile_layer(
                        right_image,
                        right_vis,
                        right_names[right_dropdown_index],
                    )
                    right_layer.url = right_image.url
                except Exception as e:
                    print(e)
                    return

        right_dropdown.observe(right_dropdown_change, names="value")

        try:

            split_control = ipyleaflet.SplitMapControl(
                left_layer=left_layer, right_layer=right_layer
            )
            self.add_control(split_control)

        except Exception as e:
            raise Exception(e)

    def basemap_demo(self):
        """A demo for using geemap basemaps."""
        dropdown = widgets.Dropdown(
            options=list(basemap_tiles.keys()),
            value="HYBRID",
            description="Basemaps",
        )

        def on_click(change):
            basemap_name = change["new"]
            old_basemap = self.layers[-1]
            self.substitute_layer(old_basemap, basemap_tiles[basemap_name])

        dropdown.observe(on_click, "value")
        basemap_control = WidgetControl(widget=dropdown, position="topright")
        self.add_control(basemap_control)

    def add_legend(
        self,
        legend_title="Legend",
        legend_dict=None,
        legend_keys=None,
        legend_colors=None,
        position="bottomright",
        builtin_legend=None,
        layer_name=None,
        **kwargs,
    ):
        """Adds a customized basemap to the map.

        Args:
            legend_title (str, optional): Title of the legend. Defaults to 'Legend'.
            legend_dict (dict, optional): A dictionary containing legend items as keys and color as values. If provided, legend_keys and legend_colors will be ignored. Defaults to None.
            legend_keys (list, optional): A list of legend keys. Defaults to None.
            legend_colors (list, optional): A list of legend colors. Defaults to None.
            position (str, optional): Position of the legend. Defaults to 'bottomright'.
            builtin_legend (str, optional): Name of the builtin legend to add to the map. Defaults to None.
            layer_name (str, optional): Layer name of the legend to be associated with. Defaults to None.

        """
        import pkg_resources
        from IPython.display import display

        pkg_dir = os.path.dirname(
            pkg_resources.resource_filename("geemap", "geemap.py")
        )
        legend_template = os.path.join(pkg_dir, "data/template/legend.html")

        if "min_width" not in kwargs.keys():
            min_width = None
        if "max_width" not in kwargs.keys():
            max_width = None
        else:
            max_width = kwargs["max_width"]
        if "min_height" not in kwargs.keys():
            min_height = None
        else:
            min_height = kwargs["min_height"]
        if "max_height" not in kwargs.keys():
            max_height = None
        else:
            max_height = kwargs["max_height"]
        if "height" not in kwargs.keys():
            height = None
        else:
            height = kwargs["height"]
        if "width" not in kwargs.keys():
            width = None
        else:
            width = kwargs["width"]

        if width is None:
            max_width = "300px"
        if height is None:
            max_height = "400px"

        if not os.path.exists(legend_template):
            print("The legend template does not exist.")
            return

        if legend_keys is not None:
            if not isinstance(legend_keys, list):
                print("The legend keys must be a list.")
                return
        else:
            legend_keys = ["One", "Two", "Three", "Four", "ect"]

        if legend_colors is not None:
            if not isinstance(legend_colors, list):
                print("The legend colors must be a list.")
                return
            elif all(isinstance(item, tuple) for item in legend_colors):
                try:
                    legend_colors = [rgb_to_hex(x) for x in legend_colors]
                except Exception as e:
                    print(e)
            elif all(
                (item.startswith("#") and len(item) == 7) for item in legend_colors
            ):
                pass
            elif all((len(item) == 6) for item in legend_colors):
                pass
            else:
                print("The legend colors must be a list of tuples.")
                return
        else:
            legend_colors = [
                "#8DD3C7",
                "#FFFFB3",
                "#BEBADA",
                "#FB8072",
                "#80B1D3",
            ]

        if len(legend_keys) != len(legend_colors):
            print("The legend keys and values must be the same length.")
            return

        allowed_builtin_legends = builtin_legends.keys()
        if builtin_legend is not None:
            if builtin_legend not in allowed_builtin_legends:
                print(
                    "The builtin legend must be one of the following: {}".format(
                        ", ".join(allowed_builtin_legends)
                    )
                )
                return
            else:
                legend_dict = builtin_legends[builtin_legend]
                legend_keys = list(legend_dict.keys())
                legend_colors = list(legend_dict.values())

        if legend_dict is not None:
            if not isinstance(legend_dict, dict):
                print("The legend dict must be a dictionary.")
                return
            else:
                legend_keys = list(legend_dict.keys())
                legend_colors = list(legend_dict.values())
                if all(isinstance(item, tuple) for item in legend_colors):
                    try:
                        legend_colors = [rgb_to_hex(x) for x in legend_colors]
                    except Exception as e:
                        print(e)

        allowed_positions = [
            "topleft",
            "topright",
            "bottomleft",
            "bottomright",
        ]
        if position not in allowed_positions:
            print(
                "The position must be one of the following: {}".format(
                    ", ".join(allowed_positions)
                )
            )
            return

        header = []
        content = []
        footer = []

        with open(legend_template) as f:
            lines = f.readlines()
            lines[3] = lines[3].replace("Legend", legend_title)
            header = lines[:6]
            footer = lines[11:]

        for index, key in enumerate(legend_keys):
            color = legend_colors[index]
            if not color.startswith("#"):
                color = "#" + color
            item = "      <li><span style='background:{};'></span>{}</li>\n".format(
                color, key
            )
            content.append(item)

        legend_html = header + content + footer
        legend_text = "".join(legend_html)

        try:
            if self.legend_control is not None:
                legend_widget = self.legend_widget
                legend_widget.close()
                if self.legend_control in self.controls:
                    self.remove_control(self.legend_control)

            legend_output_widget = widgets.Output(
                layout={
                    # "border": "1px solid black",
                    "max_width": max_width,
                    "min_width": min_width,
                    "max_height": max_height,
                    "min_height": min_height,
                    "height": height,
                    "width": width,
                    "overflow": "scroll",
                }
            )
            legend_control = WidgetControl(
                widget=legend_output_widget, position=position
            )
            legend_widget = widgets.HTML(value=legend_text)
            with legend_output_widget:
                display(legend_widget)

            self.legend_widget = legend_output_widget
            self.legend_control = legend_control
            self.add_control(legend_control)

            if layer_name in self.ee_layer_names:
                self.ee_layer_dict[layer_name]["legend"] = legend_control

        except Exception as e:
            raise Exception(e)

    def add_colorbar(
        self,
        vis_params,
        cmap="gray",
        discrete=False,
        label=None,
        orientation="horizontal",
        position="bottomright",
        transparent_bg=False,
        layer_name=None,
        **kwargs,
    ):
        """Add a matplotlib colorbar to the map

        Args:
            vis_params (dict): Visualization parameters as a dictionary. See https://developers.google.com/earth-engine/guides/image_visualization for options.
            cmap (str, optional): Matplotlib colormap. Defaults to "gray". See https://matplotlib.org/3.3.4/tutorials/colors/colormaps.html#sphx-glr-tutorials-colors-colormaps-py for options.
            discrete (bool, optional): Whether to create a discrete colorbar. Defaults to False.
            label (str, optional): Label for the colorbar. Defaults to None.
            orientation (str, optional): Orientation of the colorbar, such as "vertical" and "horizontal". Defaults to "horizontal".
            position (str, optional): Position of the colorbar on the map. It can be one of: topleft, topright, bottomleft, and bottomright. Defaults to "bottomright".
            transparent_bg (bool, optional): Whether to use transparent background. Defaults to False.
            layer_name (str, optional): The layer name associated with the colorbar. Defaults to None.

        Raises:
            TypeError: If the vis_params is not a dictionary.
            ValueError: If the orientation is not either horizontal or vertical.
            ValueError: If the provided min value is not scalar type.
            ValueError: If the provided max value is not scalar type.
            ValueError: If the provided opacity value is not scalar type.
            ValueError: If cmap or palette is not provided.
        """
        import matplotlib as mpl
        import matplotlib.pyplot as plt
        import numpy as np
        import warnings

        if not isinstance(vis_params, dict):
            raise TypeError("The vis_params must be a dictionary.")

        if orientation not in ["horizontal", "vertical"]:
            raise ValueError("The orientation must be either horizontal or vertical.")

        if orientation == "horizontal":
            width, height = 6.0, 0.4
        else:
            width, height = 0.4, 4.0

        if "width" in kwargs:
            width = kwargs["width"]
            kwargs.pop("width")

        if "height" in kwargs:
            height = kwargs["height"]
            kwargs.pop("height")

        vis_keys = list(vis_params.keys())

        if "min" in vis_params:
            vmin = vis_params["min"]
            if type(vmin) not in (int, float):
                raise ValueError("The provided min value must be scalar type.")
        else:
            vmin = 0

        if "max" in vis_params:
            vmax = vis_params["max"]
            if type(vmax) not in (int, float):
                raise ValueError("The provided max value must be scalar type.")
        else:
            vmax = 1

        if "opacity" in vis_params:
            alpha = vis_params["opacity"]
            if type(alpha) not in (int, float):
                raise ValueError("The provided opacity value must be type scalar.")
        elif "alpha" in kwargs:
            alpha = kwargs["alpha"]
        else:
            alpha = 1

        if cmap is not None:

            cmap = mpl.pyplot.get_cmap(cmap)
            norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

        if "palette" in vis_keys:
            hexcodes = vis_params["palette"]
            hexcodes = [i if i[0] == "#" else "#" + i for i in hexcodes]

            if discrete:
                cmap = mpl.colors.ListedColormap(hexcodes)
                vals = np.linspace(vmin, vmax, cmap.N + 1)
                norm = mpl.colors.BoundaryNorm(vals, cmap.N)

            else:
                cmap = mpl.colors.LinearSegmentedColormap.from_list(
                    "custom", hexcodes, N=256
                )
                norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

        elif cmap is not None:

            cmap = mpl.pyplot.get_cmap(cmap)
            norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

        else:
            raise ValueError(
                'cmap keyword or "palette" key in vis_params must be provided.'
            )

        _, ax = plt.subplots(figsize=(width, height))
        cb = mpl.colorbar.ColorbarBase(
            ax, norm=norm, alpha=alpha, cmap=cmap, orientation=orientation, **kwargs
        )

        if "bands" in vis_keys:
            cb.set_label(vis_params["bands"])
        elif label is not None:
            cb.set_label(label)

        output = widgets.Output()
        colormap_ctrl = WidgetControl(
            widget=output,
            position=position,
            transparent_bg=transparent_bg,
        )
        with output:
            output.clear_output()
            plt.show()

        self.colorbar = colormap_ctrl

        if layer_name in self.ee_layer_names:
            if "colorbar" in self.ee_layer_dict[layer_name]:
                self.remove_control(self.ee_layer_dict[layer_name]["colorbar"])
            self.ee_layer_dict[layer_name]["colorbar"] = colormap_ctrl

        self.add_control(colormap_ctrl)

    def add_colorbar_branca(
        self,
        colors,
        vmin=0,
        vmax=1.0,
        index=None,
        caption="",
        categorical=False,
        step=None,
        height="45px",
        transparent_bg=False,
        position="bottomright",
        layer_name=None,
        **kwargs,
    ):
        """Add a branca colorbar to the map.

        Args:
            colors (list): The set of colors to be used for interpolation. Colors can be provided in the form: * tuples of RGBA ints between 0 and 255 (e.g: (255, 255, 0) or (255, 255, 0, 255)) * tuples of RGBA floats between 0. and 1. (e.g: (1.,1.,0.) or (1., 1., 0., 1.)) * HTML-like string (e.g: “#ffff00) * a color name or shortcut (e.g: “y” or “yellow”)
            vmin (int, optional): The minimal value for the colormap. Values lower than vmin will be bound directly to colors[0].. Defaults to 0.
            vmax (float, optional): The maximal value for the colormap. Values higher than vmax will be bound directly to colors[-1]. Defaults to 1.0.
            index (list, optional):The values corresponding to each color. It has to be sorted, and have the same length as colors. If None, a regular grid between vmin and vmax is created.. Defaults to None.
            caption (str, optional): The caption for the colormap. Defaults to "".
            categorical (bool, optional): Whether or not to create a categorical colormap. Defaults to False.
            step (int, optional): The step to split the LinearColormap into a StepColormap. Defaults to None.
            height (str, optional): The height of the colormap widget. Defaults to "45px".
            transparent_bg (bool, optional): Whether to use transparent background for the colormap widget. Defaults to True.
            position (str, optional): The position for the colormap widget. Defaults to "bottomright".
            layer_name (str, optional): Layer name of the colorbar to be associated with. Defaults to None.

        """
        from box import Box
        from branca.colormap import LinearColormap

        output = widgets.Output()
        output.layout.height = height

        if "width" in kwargs.keys():
            output.layout.width = kwargs["width"]

        if isinstance(colors, Box):
            try:
                colors = list(colors["default"])
            except Exception as e:
                print("The provided color list is invalid.")
                raise Exception(e)

        if all(len(color) == 6 for color in colors):
            colors = ["#" + color for color in colors]

        colormap = LinearColormap(
            colors=colors, index=index, vmin=vmin, vmax=vmax, caption=caption
        )

        if categorical:
            if step is not None:
                colormap = colormap.to_step(step)
            elif index is not None:
                colormap = colormap.to_step(len(index) - 1)
            else:
                colormap = colormap.to_step(3)

        colormap_ctrl = WidgetControl(
            widget=output,
            position=position,
            transparent_bg=transparent_bg,
            **kwargs,
        )
        with output:
            output.clear_output()
            display(colormap)

        self.colorbar = colormap_ctrl
        self.add_control(colormap_ctrl)

        if layer_name in self.ee_layer_names:
            self.ee_layer_dict[layer_name]["colorbar"] = colormap_ctrl

    def remove_colorbar(self):
        """Remove colorbar from the map."""
        if self.colorbar is not None:
            self.remove_control(self.colorbar)

    def image_overlay(self, url, bounds, name):
        """Overlays an image from the Internet or locally on the map.

        Args:
            url (str): http URL or local file path to the image.
            bounds (tuple): bounding box of the image in the format of (lower_left(lat, lon), upper_right(lat, lon)), such as ((13, -130), (32, -100)).
            name (str): name of the layer to show on the layer control.
        """
        from base64 import b64encode
        from PIL import Image, ImageSequence
        from io import BytesIO

        try:
            if not url.startswith("http"):

                if not os.path.exists(url):
                    print("The provided file does not exist.")
                    return

                ext = os.path.splitext(url)[1][1:]  # file extension
                image = Image.open(url)

                f = BytesIO()
                if ext.lower() == "gif":
                    frames = []
                    # Loop over each frame in the animated image
                    for frame in ImageSequence.Iterator(image):
                        frame = frame.convert("RGBA")
                        b = BytesIO()
                        frame.save(b, format="gif")
                        frame = Image.open(b)
                        frames.append(frame)
                    frames[0].save(
                        f,
                        format="GIF",
                        save_all=True,
                        append_images=frames[1:],
                        loop=0,
                    )
                else:
                    image.save(f, ext)

                data = b64encode(f.getvalue())
                data = data.decode("ascii")
                url = "data:image/{};base64,".format(ext) + data
            img = ipyleaflet.ImageOverlay(url=url, bounds=bounds, name=name)
            self.add_layer(img)
        except Exception as e:
            print(e)

    def video_overlay(self, url, bounds, name):
        """Overlays a video from the Internet on the map.

        Args:
            url (str): http URL of the video, such as "https://www.mapbox.com/bites/00188/patricia_nasa.webm"
            bounds (tuple): bounding box of the video in the format of (lower_left(lat, lon), upper_right(lat, lon)), such as ((13, -130), (32, -100)).
            name (str): name of the layer to show on the layer control.
        """
        try:
            video = ipyleaflet.VideoOverlay(url=url, bounds=bounds, name=name)
            self.add_layer(video)
        except Exception as e:
            print(e)

    def add_landsat_ts_gif(
        self,
        layer_name="Timelapse",
        roi=None,
        label=None,
        start_year=1984,
        end_year=2019,
        start_date="06-10",
        end_date="09-20",
        bands=["NIR", "Red", "Green"],
        vis_params=None,
        dimensions=768,
        frames_per_second=10,
        font_size=30,
        font_color="white",
        add_progress_bar=True,
        progress_bar_color="white",
        progress_bar_height=5,
        out_gif=None,
        download=False,
        apply_fmask=True,
        nd_bands=None,
        nd_threshold=0,
        nd_palette=["black", "blue"],
    ):
        """Adds a Landsat timelapse to the map.

        Args:
            layer_name (str, optional): Layer name to show under the layer control. Defaults to 'Timelapse'.
            roi (object, optional): Region of interest to create the timelapse. Defaults to None.
            label (str, optional): A label to shown on the GIF, such as place name. Defaults to None.
            start_year (int, optional): Starting year for the timelapse. Defaults to 1984.
            end_year (int, optional): Ending year for the timelapse. Defaults to 2019.
            start_date (str, optional): Starting date (month-day) each year for filtering ImageCollection. Defaults to '06-10'.
            end_date (str, optional): Ending date (month-day) each year for filtering ImageCollection. Defaults to '09-20'.
            bands (list, optional): Three bands selected from ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2', 'pixel_qa']. Defaults to ['NIR', 'Red', 'Green'].
            vis_params (dict, optional): Visualization parameters. Defaults to None.
            dimensions (int, optional): a number or pair of numbers in format WIDTHxHEIGHT) Maximum dimensions of the thumbnail to render, in pixels. If only one number is passed, it is used as the maximum, and the other dimension is computed by proportional scaling. Defaults to 768.
            frames_per_second (int, optional): Animation speed. Defaults to 10.
            font_size (int, optional): Font size of the animated text and label. Defaults to 30.
            font_color (str, optional): Font color of the animated text and label. Defaults to 'black'.
            add_progress_bar (bool, optional): Whether to add a progress bar at the bottom of the GIF. Defaults to True.
            progress_bar_color (str, optional): Color for the progress bar. Defaults to 'white'.
            progress_bar_height (int, optional): Height of the progress bar. Defaults to 5.
            out_gif (str, optional): File path to the output animated GIF. Defaults to None.
            download (bool, optional): Whether to download the gif. Defaults to False.
            apply_fmask (bool, optional): Whether to apply Fmask (Function of mask) for automated clouds, cloud shadows, snow, and water masking.
            nd_bands (list, optional): A list of names specifying the bands to use, e.g., ['Green', 'SWIR1']. The normalized difference is computed as (first − second) / (first + second). Note that negative input values are forced to 0 so that the result is confined to the range (-1, 1).
            nd_threshold (float, optional): The threshold for extacting pixels from the normalized difference band.
            nd_palette (str, optional): The color palette to use for displaying the normalized difference band.

        """
        try:

            if roi is None:
                if self.draw_last_feature is not None:
                    feature = self.draw_last_feature
                    roi = feature.geometry()
                else:
                    roi = ee.Geometry.Polygon(
                        [
                            [
                                [-115.471773, 35.892718],
                                [-115.471773, 36.409454],
                                [-114.271283, 36.409454],
                                [-114.271283, 35.892718],
                                [-115.471773, 35.892718],
                            ]
                        ],
                        None,
                        False,
                    )
            elif isinstance(roi, ee.Feature) or isinstance(roi, ee.FeatureCollection):
                roi = roi.geometry()
            elif isinstance(roi, ee.Geometry):
                pass
            else:
                print("The provided roi is invalid. It must be an ee.Geometry")
                return

            geojson = ee_to_geojson(roi)
            bounds = minimum_bounding_box(geojson)
            geojson = adjust_longitude(geojson)
            roi = ee.Geometry(geojson)

            in_gif = landsat_ts_gif(
                roi=roi,
                out_gif=out_gif,
                start_year=start_year,
                end_year=end_year,
                start_date=start_date,
                end_date=end_date,
                bands=bands,
                vis_params=vis_params,
                dimensions=dimensions,
                frames_per_second=frames_per_second,
                apply_fmask=apply_fmask,
                nd_bands=nd_bands,
                nd_threshold=nd_threshold,
                nd_palette=nd_palette,
            )
            in_nd_gif = in_gif.replace(".gif", "_nd.gif")

            print("Adding animated text to GIF ...")
            add_text_to_gif(
                in_gif,
                in_gif,
                xy=("2%", "2%"),
                text_sequence=start_year,
                font_size=font_size,
                font_color=font_color,
                duration=int(1000 / frames_per_second),
                add_progress_bar=add_progress_bar,
                progress_bar_color=progress_bar_color,
                progress_bar_height=progress_bar_height,
            )
            if nd_bands is not None:
                add_text_to_gif(
                    in_nd_gif,
                    in_nd_gif,
                    xy=("2%", "2%"),
                    text_sequence=start_year,
                    font_size=font_size,
                    font_color=font_color,
                    duration=int(1000 / frames_per_second),
                    add_progress_bar=add_progress_bar,
                    progress_bar_color=progress_bar_color,
                    progress_bar_height=progress_bar_height,
                )

            if label is not None:
                add_text_to_gif(
                    in_gif,
                    in_gif,
                    xy=("2%", "90%"),
                    text_sequence=label,
                    font_size=font_size,
                    font_color=font_color,
                    duration=int(1000 / frames_per_second),
                    add_progress_bar=add_progress_bar,
                    progress_bar_color=progress_bar_color,
                    progress_bar_height=progress_bar_height,
                )
                # if nd_bands is not None:
                #     add_text_to_gif(in_nd_gif, in_nd_gif, xy=('2%', '90%'), text_sequence=label,
                #                     font_size=font_size, font_color=font_color, duration=int(1000 / frames_per_second), add_progress_bar=add_progress_bar, progress_bar_color=progress_bar_color, progress_bar_height=progress_bar_height)

            if is_tool("ffmpeg"):
                reduce_gif_size(in_gif)
                if nd_bands is not None:
                    reduce_gif_size(in_nd_gif)

            print("Adding GIF to the map ...")
            self.image_overlay(url=in_gif, bounds=bounds, name=layer_name)
            if nd_bands is not None:
                self.image_overlay(
                    url=in_nd_gif, bounds=bounds, name=layer_name + " ND"
                )
            print("The timelapse has been added to the map.")

            if download:
                link = create_download_link(
                    in_gif,
                    title="Click here to download the Landsat timelapse: ",
                )
                display(link)
                if nd_bands is not None:
                    link2 = create_download_link(
                        in_nd_gif,
                        title="Click here to download the Normalized Difference Index timelapse: ",
                    )
                    display(link2)

        except Exception as e:
            raise Exception(e)

    def to_html(self, outfile, title="My Map", width="100%", height="880px"):
        """Saves the map as a HTML file.

        Args:
            outfile (str): The output file path to the HTML file.
            title (str, optional): The title of the HTML file. Defaults to 'My Map'.
            width (str, optional): The width of the map in pixels or percentage. Defaults to '100%'.
            height (str, optional): The height of the map in pixels. Defaults to '880px'.
        """
        try:

            if not outfile.endswith(".html"):
                print("The output file must end with .html")
                return

            out_dir = os.path.dirname(outfile)
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)

            before_width = self.layout.width
            before_height = self.layout.height

            if not isinstance(width, str):
                print("width must be a string.")
                return
            elif width.endswith("px") or width.endswith("%"):
                pass
            else:
                print("width must end with px or %")
                return

            if not isinstance(height, str):
                print("height must be a string.")
                return
            elif not height.endswith("px"):
                print("height must end with px")
                return

            self.layout.width = width
            self.layout.height = height

            self.save(outfile, title=title)

            self.layout.width = before_width
            self.layout.height = before_height

        except Exception as e:
            raise Exception(e)

    def to_image(self, outfile=None, monitor=1):
        """Saves the map as a PNG or JPG image.

        Args:
            outfile (str, optional): The output file path to the image. Defaults to None.
            monitor (int, optional): The monitor to take the screenshot. Defaults to 1.
        """
        if outfile is None:
            outfile = os.path.join(os.getcwd(), "my_map.png")

        if outfile.endswith(".png") or outfile.endswith(".jpg"):
            pass
        else:
            print("The output file must be a PNG or JPG image.")
            return

        work_dir = os.path.dirname(outfile)
        if not os.path.exists(work_dir):
            os.makedirs(work_dir)

        screenshot = screen_capture(outfile, monitor)
        self.screenshot = screenshot

    def toolbar_reset(self):
        """Reset the toolbar so that no tool is selected."""
        toolbar_grid = self.toolbar
        for tool in toolbar_grid.children:
            tool.value = False

    def add_raster(
        self,
        image,
        bands=None,
        layer_name=None,
        colormap=None,
        x_dim="x",
        y_dim="y",
    ):
        """Adds a local raster dataset to the map.

        Args:
            image (str): The image file path.
            bands (int or list, optional): The image bands to use. It can be either a nubmer (e.g., 1) or a list (e.g., [3, 2, 1]). Defaults to None.
            layer_name (str, optional): The layer name to use for the raster. Defaults to None.
            colormap (str, optional): The name of the colormap to use for the raster, such as 'gray' and 'terrain'. More can be found at https://matplotlib.org/3.1.0/tutorials/colors/colormaps.html. Defaults to None.
            x_dim (str, optional): The x dimension. Defaults to 'x'.
            y_dim (str, optional): The y dimension. Defaults to 'y'.
        """
        try:
            import xarray_leaflet

        except Exception:
            # import platform
            # if platform.system() != "Windows":
            #     # install_from_github(
            #     #     url='https://github.com/davidbrochart/xarray_leaflet')
            #     check_install('xarray_leaflet')
            #     import xarray_leaflet
            # else:
            raise ImportError(
                "You need to install xarray_leaflet first. See https://github.com/davidbrochart/xarray_leaflet"
            )

        import warnings
        import numpy as np
        import rioxarray

        # import xarray as xr
        import matplotlib.pyplot as plt

        warnings.simplefilter("ignore")

        if not os.path.exists(image):
            print("The image file does not exist.")
            return

        if colormap is None:
            colormap = plt.cm.inferno

        if layer_name is None:
            layer_name = "Layer_" + random_string()

        if isinstance(colormap, str):
            colormap = plt.cm.get_cmap(name=colormap)

        da = rioxarray.open_rasterio(image, masked=True)

        # print(da.rio.nodata)

        multi_band = False
        if len(da.band) > 1:
            multi_band = True
            if bands is None:
                bands = [3, 2, 1]
        else:
            bands = 1

        if multi_band:
            da = da.rio.write_nodata(0)
        else:
            da = da.rio.write_nodata(np.nan)
        da = da.sel(band=bands)

        # crs = da.rio.crs
        # nan = da.attrs['nodatavals'][0]
        # da = da / da.max()
        # # if multi_band:
        # da = xr.where(da == nan, np.nan, da)
        # da = da.rio.write_nodata(0)
        # da = da.rio.write_crs(crs)

        if multi_band:
            layer = da.leaflet.plot(self, x_dim=x_dim, y_dim=y_dim, rgb_dim="band")
        else:
            layer = da.leaflet.plot(self, x_dim=x_dim, y_dim=y_dim, colormap=colormap)

        layer.name = layer_name

    def remove_drawn_features(self):
        """Removes user-drawn geometries from the map"""
        if self.draw_layer is not None:
            self.remove_layer(self.draw_layer)
            self.draw_count = 0
            self.draw_features = []
            self.draw_last_feature = None
            self.draw_layer = None
            self.draw_last_json = None
            self.draw_last_bounds = None
            self.user_roi = None
            self.user_rois = None
            self.chart_values = []
            self.chart_points = []
            self.chart_labels = None
        if self.draw_control is not None:
            self.draw_control.clear()

    def remove_last_drawn(self):
        """Removes user-drawn geometries from the map"""
        if self.draw_layer is not None:
            collection = ee.FeatureCollection(self.draw_features[:-1])
            ee_draw_layer = ee_tile_layer(
                collection, {"color": "blue"}, "Drawn Features", True, 0.5
            )
            if self.draw_count == 1:
                self.remove_drawn_features()
            else:
                self.substitute_layer(self.draw_layer, ee_draw_layer)
                self.draw_layer = ee_draw_layer
                self.draw_count -= 1
                self.draw_features = self.draw_features[:-1]
                self.draw_last_feature = self.draw_features[-1]
                self.draw_layer = ee_draw_layer
                self.draw_last_json = None
                self.draw_last_bounds = None
                self.user_roi = ee.Feature(
                    collection.toList(collection.size()).get(
                        collection.size().subtract(1)
                    )
                ).geometry()
                self.user_rois = collection
                self.chart_values = self.chart_values[:-1]
                self.chart_points = self.chart_points[:-1]
                # self.chart_labels = None

    def extract_values_to_points(self, filename):
        """Exports pixel values to a csv file based on user-drawn geometries.

        Args:
            filename (str): The output file path to the csv file or shapefile.
        """
        import csv

        filename = os.path.abspath(filename)
        allowed_formats = ["csv", "shp"]
        ext = filename[-3:]

        if ext not in allowed_formats:
            print(
                "The output file must be one of the following: {}".format(
                    ", ".join(allowed_formats)
                )
            )
            return

        out_dir = os.path.dirname(filename)
        out_csv = filename[:-3] + "csv"
        out_shp = filename[:-3] + "shp"
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        count = len(self.chart_points)
        out_list = []
        if count > 0:
            header = ["id", "longitude", "latitude"] + self.chart_labels
            out_list.append(header)

            for i in range(0, count):
                id = i + 1
                line = [id] + self.chart_points[i] + self.chart_values[i]
                out_list.append(line)

            with open(out_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(out_list)

            if ext == "csv":
                print("The csv file has been saved to: {}".format(out_csv))
            else:
                csv_to_shp(out_csv, out_shp)
                print("The shapefile has been saved to: {}".format(out_shp))

    def create_vis_widget(self, layer_dict):
        """Create a GUI for changing layer visualization parameters interactively.

        Args:
            layer_dict (dict): A dict containning information about the layer. It is an element from Map.ee_layer_dict.

        Returns:
            object: An ipywidget.
        """

        import branca.colormap as cmap

        ee_object = layer_dict["ee_object"]
        ee_layer = layer_dict["ee_layer"]
        vis_params = layer_dict["vis_params"]

        layer_name = ee_layer.name
        layer_opacity = ee_layer.opacity

        band_names = None
        # band_count = 1
        min_value = 0
        max_value = 100
        sel_bands = None
        layer_palette = []
        layer_gamma = 1
        left_value = 0
        right_value = 10000

        self.colorbar_widget = widgets.Output(layout=widgets.Layout(height="45px"))
        self.colorbar_ctrl = WidgetControl(
            widget=self.colorbar_widget, position="bottomright"
        )
        self.add_control(self.colorbar_ctrl)

        def vdir(obj):  # Get branca colormap list
            return [x for x in dir(obj) if not x.startswith("_")]

        if isinstance(ee_object, ee.Image):
            band_names = ee_object.bandNames().getInfo()
            band_count = len(band_names)

            if "min" in vis_params.keys():
                min_value = vis_params["min"]
                if min_value < left_value:
                    left_value = min_value - max_value
            if "max" in vis_params.keys():
                max_value = vis_params["max"]
                right_value = 2 * max_value
            if "gamma" in vis_params.keys():
                layer_gamma = vis_params["gamma"]
            if "bands" in vis_params.keys():
                sel_bands = vis_params["bands"]
            if "palette" in vis_params.keys():
                layer_palette = vis_params["palette"]

            vis_widget = widgets.VBox(
                layout=widgets.Layout(padding="5px 5px 5px 8px", width="330px")
            )
            label = widgets.Label(value=f"{layer_name} visualization parameters")

            radio1 = widgets.RadioButtons(
                options=["1 band (Grayscale)"], layout={"width": "max-content"}
            )
            radio2 = widgets.RadioButtons(
                options=["3 bands (RGB)"], layout={"width": "max-content"}
            )
            radio1.index = None
            radio2.index = None

            dropdown_width = "98px"
            band1_dropdown = widgets.Dropdown(
                options=band_names,
                value=band_names[0],
                layout=widgets.Layout(width=dropdown_width),
            )
            band2_dropdown = widgets.Dropdown(
                options=band_names,
                value=band_names[0],
                layout=widgets.Layout(width=dropdown_width),
            )
            band3_dropdown = widgets.Dropdown(
                options=band_names,
                value=band_names[0],
                layout=widgets.Layout(width=dropdown_width),
            )

            bands_hbox = widgets.HBox()

            legend_chk = widgets.Checkbox(
                value=False,
                description="Legend",
                indent=False,
                layout=widgets.Layout(width="70px"),
            )

            color_picker = widgets.ColorPicker(
                concise=False,
                value="#000000",
                layout=widgets.Layout(width="116px"),
                style={"description_width": "initial"},
            )

            add_color = widgets.Button(
                icon="plus",
                tooltip="Add a hex color string to the palette",
                layout=widgets.Layout(width="32px"),
            )

            del_color = widgets.Button(
                icon="minus",
                tooltip="Remove a hex color string from the palette",
                layout=widgets.Layout(width="32px"),
            )

            reset_color = widgets.Button(
                icon="eraser",
                tooltip="Remove all color strings from the palette",
                layout=widgets.Layout(width="34px"),
            )

            classes = widgets.Dropdown(
                options=["Any"] + [str(i) for i in range(3, 13)],
                description="Classes:",
                layout=widgets.Layout(width="115px"),
                style={"description_width": "initial"},
            )

            colormap = widgets.Dropdown(
                options=vdir(cmap.step),
                value=None,
                description="Colormap:",
                layout=widgets.Layout(width="181px"),
                style={"description_width": "initial"},
            )

            def classes_changed(change):
                colormap_options = vdir(cmap.step)
                if change["new"]:
                    selected = change["owner"].value
                    if selected == "Any":
                        colormap.options = colormap_options
                    else:
                        sel_class = selected.zfill(2)
                        colormap.options = [
                            color
                            for color in colormap_options
                            if color[-2:] == sel_class
                        ]

            classes.observe(classes_changed, "value")

            palette = widgets.Text(
                value=", ".join(layer_palette),
                placeholder="List of hex color code (RRGGBB)",
                description="Palette:",
                tooltip="Enter a list of hex color code (RRGGBB)",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "initial"},
            )

            def add_color_clicked(b):
                if color_picker.value is not None:
                    if len(palette.value) == 0:
                        palette.value = color_picker.value[1:]
                    else:
                        palette.value += ", " + color_picker.value[1:]

            def del_color_clicked(b):
                if "," in palette.value:
                    items = [item.strip() for item in palette.value.split(",")]
                    palette.value = ", ".join(items[:-1])
                else:
                    palette.value = ""

            def reset_color_clicked(b):
                palette.value = ""

            add_color.on_click(add_color_clicked)
            del_color.on_click(del_color_clicked)
            reset_color.on_click(reset_color_clicked)

            spacer = widgets.Label(layout=widgets.Layout(width="5px"))
            v_spacer = widgets.Label(layout=widgets.Layout(height="5px"))
            radio_btn = widgets.HBox([radio1, spacer, spacer, spacer, radio2])

            value_range = widgets.FloatRangeSlider(
                value=[min_value, max_value],
                min=left_value,
                max=right_value,
                step=0.1,
                description="Range:",
                disabled=False,
                continuous_update=False,
                readout=True,
                readout_format=".1f",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "45px"},
            )

            range_hbox = widgets.HBox([value_range, spacer])

            opacity = widgets.FloatSlider(
                value=layer_opacity,
                min=0,
                max=1,
                step=0.01,
                description="Opacity:",
                continuous_update=False,
                readout=True,
                readout_format=".2f",
                layout=widgets.Layout(width="320px"),
                style={"description_width": "50px"},
            )

            gamma = widgets.FloatSlider(
                value=layer_gamma,
                min=0.1,
                max=10,
                step=0.01,
                description="Gamma:",
                continuous_update=False,
                readout=True,
                readout_format=".2f",
                layout=widgets.Layout(width="320px"),
                style={"description_width": "50px"},
            )

            legend_chk = widgets.Checkbox(
                value=False,
                description="Legend",
                indent=False,
                layout=widgets.Layout(width="70px"),
            )

            linear_chk = widgets.Checkbox(
                value=True,
                description="Linear colormap",
                indent=False,
                layout=widgets.Layout(width="150px"),
            )

            step_chk = widgets.Checkbox(
                value=False,
                description="Step colormap",
                indent=False,
                layout=widgets.Layout(width="140px"),
            )

            legend_title = widgets.Text(
                value="Legend",
                description="Legend title:",
                tooltip="Enter a title for the legend",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "initial"},
            )

            legend_labels = widgets.Text(
                value="Class 1, Class 2, Class 3",
                description="Legend labels:",
                tooltip="Enter a a list of labels for the legend",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "initial"},
            )

            colormap_hbox = widgets.HBox([linear_chk, step_chk])
            legend_vbox = widgets.VBox()

            def linear_chk_changed(change):

                if change["new"]:
                    step_chk.value = False
                    legend_vbox.children = [colormap_hbox]
                else:
                    step_chk.value = True

            def step_chk_changed(change):

                if change["new"]:
                    linear_chk.value = False
                    legend_vbox.children = [
                        colormap_hbox,
                        legend_title,
                        legend_labels,
                    ]
                else:
                    linear_chk.value = True

            linear_chk.observe(linear_chk_changed, "value")
            step_chk.observe(step_chk_changed, "value")

            def colormap_changed(change):
                if change["new"]:
                    cmap_colors = cmap.linear.__dict__["_schemes"][colormap.value]

                    colorbar = cmap.LinearColormap(
                        colors=cmap_colors,
                        vmin=value_range.value[0],
                        vmax=value_range.value[1],
                    )

                    if step_chk.value:
                        colorbar = colorbar.to_step(len(cmap_colors))

                    palette.value = ", ".join([color[1:] for color in cmap_colors])

                    if self.colorbar_widget is None:
                        self.colorbar_widget = widgets.Output(
                            layout=widgets.Layout(height="45px")
                        )

                    if self.colorbar_ctrl is None:
                        self.colorbar_ctrl = WidgetControl(
                            widget=self.colorbar_widget, position="bottomright"
                        )
                        self.add_control(self.colorbar_ctrl)

                    colorbar_output = self.colorbar_widget
                    with colorbar_output:
                        colorbar_output.clear_output()
                        display(colorbar)

                    if len(palette.value) > 0 and "," in palette.value:
                        labels = [
                            f"Class {i+1}" for i in range(len(palette.value.split(",")))
                        ]
                        legend_labels.value = ", ".join(labels)

            colormap.observe(colormap_changed, "value")

            btn_width = "97.5px"
            import_btn = widgets.Button(
                description="Import",
                button_style="primary",
                tooltip="Import vis params to notebook",
                layout=widgets.Layout(width=btn_width),
            )

            apply_btn = widgets.Button(
                description="Apply",
                tooltip="Apply vis params to the layer",
                layout=widgets.Layout(width=btn_width),
            )

            close_btn = widgets.Button(
                description="Close",
                tooltip="Close vis params diaglog",
                layout=widgets.Layout(width=btn_width),
            )

            def import_btn_clicked(b):

                vis = {}
                if radio1.index == 0:
                    vis["bands"] = [band1_dropdown.value]
                    if len(palette.value) > 0:
                        vis["palette"] = palette.value.split(",")
                else:
                    vis["bands"] = [
                        band1_dropdown.value,
                        band2_dropdown.value,
                        band3_dropdown.value,
                    ]

                vis["min"] = value_range.value[0]
                vis["max"] = value_range.value[1]
                vis["opacity"] = opacity.value
                vis["gamma"] = gamma.value

                create_code_cell(f"vis_params = {str(vis)}")

            def apply_btn_clicked(b):

                vis = {}
                if radio1.index == 0:
                    vis["bands"] = [band1_dropdown.value]
                    if len(palette.value) > 0:
                        vis["palette"] = palette.value.split(",")
                else:
                    vis["bands"] = [
                        band1_dropdown.value,
                        band2_dropdown.value,
                        band3_dropdown.value,
                    ]
                    vis["gamma"] = gamma.value

                vis["min"] = value_range.value[0]
                vis["max"] = value_range.value[1]

                self.addLayer(ee_object, vis, layer_name, True, opacity.value)
                ee_layer.visible = False

                if legend_chk.value:

                    if (
                        self.colorbar_ctrl is not None
                        and self.colorbar_ctrl in self.controls
                    ):
                        self.remove_control(self.colorbar_ctrl)
                        self.colorbar_ctrl.close()
                        self.colorbar_widget.close()

                    if (
                        "colorbar" in layer_dict.keys()
                        and layer_dict["colorbar"] in self.controls
                    ):
                        self.remove_control(layer_dict["colorbar"])
                        layer_dict["colorbar"] = None

                    if linear_chk.value:

                        if (
                            "legend" in layer_dict.keys()
                            and layer_dict["legend"] in self.controls
                        ):
                            self.remove_control(layer_dict["legend"])
                            layer_dict["legend"] = None

                        if len(palette.value) > 0 and "," in palette.value:
                            colors = [
                                "#" + color.strip()
                                for color in palette.value.split(",")
                            ]

                            self.add_colorbar_branca(
                                colors=colors,
                                vmin=value_range.value[0],
                                vmax=value_range.value[1],
                                layer_name=layer_name,
                            )

                    elif step_chk.value:

                        if len(palette.value) > 0 and "," in palette.value:
                            colors = [
                                "#" + color.strip()
                                for color in palette.value.split(",")
                            ]
                            labels = [
                                label.strip()
                                for label in legend_labels.value.split(",")
                            ]

                            self.add_legend(
                                legend_title=legend_title.value,
                                legend_keys=labels,
                                legend_colors=colors,
                                layer_name=layer_name,
                            )
                else:

                    # if (
                    #     self.colorbar_ctrl is not None
                    #     and self.colorbar_ctrl in self.controls
                    # ):
                    #     self.remove_control(self.colorbar_ctrl)
                    #     self.colorbar_widget.close()

                    if (
                        "colorbar" in layer_dict.keys()
                        and layer_dict["colorbar"] in self.controls
                    ):
                        self.remove_control(layer_dict["colorbar"])
                        layer_dict["colorbar"] = None
                    if (
                        "legend" in layer_dict.keys()
                        and layer_dict["legend"] in self.controls
                    ):
                        self.remove_control(layer_dict["legend"])
                        layer_dict["legend"] = None

            def close_btn_clicked(b):
                if self.vis_control in self.controls:
                    self.remove_control(self.vis_control)
                    self.vis_control = None
                    self.vis_widget.close()

                if (
                    self.colorbar_ctrl is not None
                    and self.colorbar_ctrl in self.controls
                ):
                    self.remove_control(self.colorbar_ctrl)
                    self.colorbar_ctrl = None
                    self.colorbar_widget.close()

            import_btn.on_click(import_btn_clicked)
            apply_btn.on_click(apply_btn_clicked)
            close_btn.on_click(close_btn_clicked)

            color_hbox = widgets.HBox(
                [legend_chk, color_picker, add_color, del_color, reset_color]
            )
            btn_hbox = widgets.HBox([import_btn, apply_btn, close_btn])

            gray_box = [
                label,
                radio_btn,
                bands_hbox,
                v_spacer,
                range_hbox,
                opacity,
                gamma,
                widgets.HBox([classes, colormap]),
                palette,
                color_hbox,
                legend_vbox,
                btn_hbox,
            ]

            rgb_box = [
                label,
                radio_btn,
                bands_hbox,
                v_spacer,
                range_hbox,
                opacity,
                gamma,
                btn_hbox,
            ]

            def legend_chk_changed(change):

                if change["new"]:
                    linear_chk.value = True
                    legend_vbox.children = [
                        widgets.HBox([linear_chk, step_chk]),
                        # legend_title,
                        # legend_labels,
                    ]
                else:
                    legend_vbox.children = []

            legend_chk.observe(legend_chk_changed, "value")

            if band_count < 3:
                radio1.index = 0
                band1_dropdown.layout.width = "300px"
                bands_hbox.children = [band1_dropdown]
                vis_widget.children = gray_box
                legend_chk.value = False

                if len(palette.value) > 0 and "," in palette.value:
                    colors = ["#" + color.strip() for color in palette.value.split(",")]
                    colorbar = cmap.LinearColormap(
                        colors=colors,
                        vmin=value_range.value[0],
                        vmax=value_range.value[1],
                    )
                    self.colorbar_widget.clear_output()
                    with self.colorbar_widget:
                        display(colorbar)

            else:
                radio2.index = 0
                if (sel_bands is None) or (len(sel_bands) < 2):
                    sel_bands = band_names[0:3]
                band1_dropdown.value = sel_bands[0]
                band2_dropdown.value = sel_bands[1]
                band3_dropdown.value = sel_bands[2]
                bands_hbox.children = [
                    band1_dropdown,
                    band2_dropdown,
                    band3_dropdown,
                ]
                vis_widget.children = rgb_box

            def radio1_observer(sender):
                radio2.unobserve(radio2_observer, names=["value"])
                radio2.index = None
                radio2.observe(radio2_observer, names=["value"])
                band1_dropdown.layout.width = "300px"
                bands_hbox.children = [band1_dropdown]
                palette.value = ", ".join(layer_palette)
                palette.disabled = False
                color_picker.disabled = False
                add_color.disabled = False
                del_color.disabled = False
                reset_color.disabled = False
                vis_widget.children = gray_box

                if len(palette.value) > 0 and "," in palette.value:
                    colors = ["#" + color.strip() for color in palette.value.split(",")]
                    colorbar = cmap.LinearColormap(
                        colors=colors,
                        vmin=value_range.value[0],
                        vmax=value_range.value[1],
                    )

                    if self.colorbar_widget is None:
                        self.colorbar_widget = widgets.Output(
                            layout=widgets.Layout(height="45px")
                        )
                    if self.colorbar_ctrl is None:
                        self.colorbar_ctrl = WidgetControl(
                            widget=self.colorbar_widget, position="bottomright"
                        )
                    if self.colorbar_ctrl not in self.controls:
                        self.add_control(self.colorbar_ctrl)

                    self.colorbar_widget.clear_output()
                    with self.colorbar_widget:
                        display(colorbar)

            def radio2_observer(sender):
                radio1.unobserve(radio1_observer, names=["value"])
                radio1.index = None
                radio1.observe(radio1_observer, names=["value"])
                band1_dropdown.layout.width = dropdown_width
                bands_hbox.children = [
                    band1_dropdown,
                    band2_dropdown,
                    band3_dropdown,
                ]
                palette.value = ""
                palette.disabled = True
                color_picker.disabled = True
                add_color.disabled = True
                del_color.disabled = True
                reset_color.disabled = True
                vis_widget.children = rgb_box

                if (
                    self.colorbar_ctrl is not None
                    and self.colorbar_ctrl in self.controls
                ):
                    self.remove_control(self.colorbar_ctrl)
                    self.colorbar_ctrl.close()
                    self.colorbar_widget.close()

            radio1.observe(radio1_observer, names=["value"])
            radio2.observe(radio2_observer, names=["value"])

            return vis_widget

        elif isinstance(ee_object, ee.FeatureCollection):

            vis_widget = widgets.VBox(
                layout=widgets.Layout(padding="5px 5px 5px 8px", width="330px")
            )
            label = widgets.Label(value=f"{layer_name} visualization parameters")

            new_layer_name = widgets.Text(
                value=f"{layer_name} style",
                description="New layer name:",
                style={"description_width": "initial"},
            )

            color = widgets.ColorPicker(
                concise=False,
                value="#000000",
                description="Color:",
                layout=widgets.Layout(width="140px"),
                style={"description_width": "initial"},
            )

            color_opacity = widgets.FloatSlider(
                value=layer_opacity,
                min=0,
                max=1,
                step=0.01,
                description="Opacity:",
                continuous_update=True,
                readout=False,
                #             readout_format=".2f",
                layout=widgets.Layout(width="130px"),
                style={"description_width": "50px"},
            )

            color_opacity_label = widgets.Label(
                style={"description_width": "initial"},
                layout=widgets.Layout(padding="0px"),
            )
            widgets.jslink((color_opacity, "value"), (color_opacity_label, "value"))

            point_size = widgets.IntText(
                value=3,
                description="Point size:",
                layout=widgets.Layout(width="110px"),
                style={"description_width": "initial"},
            )

            point_shape_options = [
                "circle",
                "square",
                "diamond",
                "cross",
                "plus",
                "pentagram",
                "hexagram",
                "triangle",
                "triangle_up",
                "triangle_down",
                "triangle_left",
                "triangle_right",
                "pentagon",
                "hexagon",
                "star5",
                "star6",
            ]
            point_shape = widgets.Dropdown(
                options=point_shape_options,
                value="circle",
                description="Point shape:",
                layout=widgets.Layout(width="185px"),
                style={"description_width": "initial"},
            )

            line_width = widgets.IntText(
                value=2,
                description="Line width:",
                layout=widgets.Layout(width="110px"),
                style={"description_width": "initial"},
            )

            line_type = widgets.Dropdown(
                options=["solid", "dotted", "dashed"],
                value="solid",
                description="Line type:",
                layout=widgets.Layout(width="185px"),
                style={"description_width": "initial"},
            )

            fill_color = widgets.ColorPicker(
                concise=False,
                value="#000000",
                description="Fill Color:",
                layout=widgets.Layout(width="160px"),
                style={"description_width": "initial"},
            )

            fill_color_opacity = widgets.FloatSlider(
                value=0.66,
                min=0,
                max=1,
                step=0.01,
                description="Opacity:",
                continuous_update=True,
                readout=False,
                #             readout_format=".2f",
                layout=widgets.Layout(width="110px"),
                style={"description_width": "50px"},
            )

            fill_color_opacity_label = widgets.Label(
                style={"description_width": "initial"},
                layout=widgets.Layout(padding="0px"),
            )
            widgets.jslink(
                (fill_color_opacity, "value"),
                (fill_color_opacity_label, "value"),
            )

            color_picker = widgets.ColorPicker(
                concise=False,
                value="#000000",
                layout=widgets.Layout(width="116px"),
                style={"description_width": "initial"},
            )
            add_color = widgets.Button(
                icon="plus",
                tooltip="Add a hex color string to the palette",
                layout=widgets.Layout(width="32px"),
            )
            del_color = widgets.Button(
                icon="minus",
                tooltip="Remove a hex color string from the palette",
                layout=widgets.Layout(width="32px"),
            )
            reset_color = widgets.Button(
                icon="eraser",
                tooltip="Remove all color strings from the palette",
                layout=widgets.Layout(width="34px"),
            )

            palette = widgets.Text(
                value="",
                placeholder="List of hex code (RRGGBB) separated by comma",
                description="Palette:",
                tooltip="Enter a list of hex code (RRGGBB) separated by comma",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "initial"},
            )

            legend_title = widgets.Text(
                value="Legend",
                description="Legend title:",
                tooltip="Enter a title for the legend",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "initial"},
            )

            legend_labels = widgets.Text(
                value="Labels",
                description="Legend labels:",
                tooltip="Enter a a list of labels for the legend",
                layout=widgets.Layout(width="300px"),
                style={"description_width": "initial"},
            )

            def add_color_clicked(b):
                if color_picker.value is not None:
                    if len(palette.value) == 0:
                        palette.value = color_picker.value[1:]
                    else:
                        palette.value += ", " + color_picker.value[1:]

            def del_color_clicked(b):
                if "," in palette.value:
                    items = [item.strip() for item in palette.value.split(",")]
                    palette.value = ", ".join(items[:-1])
                else:
                    palette.value = ""

            def reset_color_clicked(b):
                palette.value = ""

            add_color.on_click(add_color_clicked)
            del_color.on_click(del_color_clicked)
            reset_color.on_click(reset_color_clicked)

            field = widgets.Dropdown(
                options=[],
                value=None,
                description="Field:",
                layout=widgets.Layout(width="140px"),
                style={"description_width": "initial"},
            )

            field_values = widgets.Dropdown(
                options=[],
                value=None,
                description="Values:",
                layout=widgets.Layout(width="156px"),
                style={"description_width": "initial"},
            )

            classes = widgets.Dropdown(
                options=["Any"] + [str(i) for i in range(3, 13)],
                description="Classes:",
                layout=widgets.Layout(width="115px"),
                style={"description_width": "initial"},
            )

            colormap = widgets.Dropdown(
                options=["viridis"],
                value="viridis",
                description="Colormap:",
                layout=widgets.Layout(width="181px"),
                style={"description_width": "initial"},
            )

            def classes_changed(change):
                colormap_options = vdir(cmap.step)
                if change["new"]:
                    selected = change["owner"].value
                    if selected == "Any":
                        colormap.options = colormap_options
                    else:
                        sel_class = selected.zfill(2)
                        colormap.options = [
                            color
                            for color in colormap_options
                            if color[-2:] == sel_class
                        ]

            classes.observe(classes_changed, "value")

            def colormap_changed(change):
                if change["new"]:
                    cmap_colors = [
                        color[1:]
                        for color in cmap.step.__dict__["_schemes"][colormap.value]
                    ]
                    palette.value = ", ".join(cmap_colors)
                    colorbar = getattr(cmap.step, colormap.value)
                    colorbar_output = self.colorbar_widget
                    with colorbar_output:
                        colorbar_output.clear_output()
                        display(colorbar)

                    if len(palette.value) > 0 and "," in palette.value:
                        labels = [
                            f"Class {i+1}" for i in range(len(palette.value.split(",")))
                        ]
                        legend_labels.value = ", ".join(labels)

            colormap.observe(colormap_changed, "value")

            btn_width = "97.5px"
            import_btn = widgets.Button(
                description="Import",
                button_style="primary",
                tooltip="Import vis params to notebook",
                layout=widgets.Layout(width=btn_width),
            )

            apply_btn = widgets.Button(
                description="Apply",
                tooltip="Apply vis params to the layer",
                layout=widgets.Layout(width=btn_width),
            )

            close_btn = widgets.Button(
                description="Close",
                tooltip="Close vis params diaglog",
                layout=widgets.Layout(width=btn_width),
            )

            style_chk = widgets.Checkbox(
                value=False,
                description="Style by attribute",
                indent=False,
                layout=widgets.Layout(width="140px"),
            )

            legend_chk = widgets.Checkbox(
                value=False,
                description="Legend",
                indent=False,
                layout=widgets.Layout(width="70px"),
            )
            compute_label = widgets.Label(value="")

            style_vbox = widgets.VBox([widgets.HBox([style_chk, compute_label])])

            def style_chk_changed(change):

                if change["new"]:

                    if (
                        self.colorbar_ctrl is not None
                        and self.colorbar_ctrl in self.controls
                    ):
                        self.remove_control(self.colorbar_ctrl)
                        self.colorbar_ctrl.close()
                        self.colorbar_widget.close()

                    self.colorbar_widget = widgets.Output(
                        layout=widgets.Layout(height="45px")
                    )
                    self.colorbar_ctrl = WidgetControl(
                        widget=self.colorbar_widget, position="bottomright"
                    )
                    self.add_control(self.colorbar_ctrl)
                    fill_color.disabled = True
                    colormap.options = vdir(cmap.step)
                    colormap.value = "viridis"
                    style_vbox.children = [
                        widgets.HBox([style_chk, compute_label]),
                        widgets.HBox([field, field_values]),
                        widgets.HBox([classes, colormap]),
                        palette,
                        widgets.HBox(
                            [
                                legend_chk,
                                color_picker,
                                add_color,
                                del_color,
                                reset_color,
                            ]
                        ),
                    ]
                    compute_label.value = "Computing ..."

                    field.options = (
                        ee.Feature(ee_object.first()).propertyNames().getInfo()
                    )
                    compute_label.value = ""
                    classes.value = "Any"
                    legend_chk.value = False

                else:
                    fill_color.disabled = False
                    style_vbox.children = [widgets.HBox([style_chk, compute_label])]
                    compute_label.value = ""
                    if (
                        self.colorbar_ctrl is not None
                        and self.colorbar_ctrl in self.controls
                    ):
                        self.remove_control(self.colorbar_ctrl)
                        self.colorbar_ctrl = None
                        self.colorbar_widget = None
                    # legend_chk.value = False

            style_chk.observe(style_chk_changed, "value")

            def legend_chk_changed(change):
                if change["new"]:
                    style_vbox.children = list(style_vbox.children) + [
                        widgets.VBox([legend_title, legend_labels])
                    ]

                    if len(palette.value) > 0 and "," in palette.value:
                        labels = [
                            f"Class {i+1}" for i in range(len(palette.value.split(",")))
                        ]
                        legend_labels.value = ", ".join(labels)

                else:
                    style_vbox.children = [
                        widgets.HBox([style_chk, compute_label]),
                        widgets.HBox([field, field_values]),
                        widgets.HBox([classes, colormap]),
                        palette,
                        widgets.HBox(
                            [
                                legend_chk,
                                color_picker,
                                add_color,
                                del_color,
                                reset_color,
                            ]
                        ),
                    ]

            legend_chk.observe(legend_chk_changed, "value")

            def field_changed(change):

                if change["new"]:
                    compute_label.value = "Computing ..."
                    options = ee_object.aggregate_array(field.value).getInfo()
                    if options is not None:
                        options = list(set(options))
                        options.sort()

                    field_values.options = options
                    compute_label.value = ""

            field.observe(field_changed, "value")

            def get_vis_params():

                vis = {}
                vis["color"] = color.value[1:] + str(
                    hex(int(color_opacity.value * 255))
                )[2:].zfill(2)
                if geometry_type(ee_object) in ["Point", "MultiPoint"]:
                    vis["pointSize"] = point_size.value
                    vis["pointShape"] = point_shape.value
                vis["width"] = line_width.value
                vis["lineType"] = line_type.value
                vis["fillColor"] = fill_color.value[1:] + str(
                    hex(int(fill_color_opacity.value * 255))
                )[2:].zfill(2)

                return vis

            def import_btn_clicked(b):

                vis = get_vis_params()
                create_code_cell(f"vis_params = {str(vis)}")

            def apply_btn_clicked(b):

                compute_label.value = "Computing ..."

                if new_layer_name.value in self.ee_layer_names:
                    old_layer = new_layer_name.value

                    if "legend" in self.ee_layer_dict[old_layer].keys():
                        legend = self.ee_layer_dict[old_layer]["legend"]
                        if legend in self.controls:
                            self.remove_control(legend)
                        legend.close()
                    if "colorbar" in self.ee_layer_dict[old_layer].keys():
                        colorbar = self.ee_layer_dict[old_layer]["colorbar"]
                        if colorbar in self.controls:
                            self.remove_control(colorbar)
                        colorbar.close()

                if not style_chk.value:
                    vis = get_vis_params()
                    self.addLayer(ee_object.style(**vis), {}, new_layer_name.value)
                    ee_object.visible = False

                elif (
                    style_chk.value and len(palette.value) > 0 and "," in palette.value
                ):
                    colors = ee.List(
                        [
                            color.strip()
                            + str(hex(int(fill_color_opacity.value * 255)))[2:].zfill(2)
                            for color in palette.value.split(",")
                        ]
                    )
                    arr = ee_object.aggregate_array(field.value).distinct().sort()
                    fc = ee_object.map(
                        lambda f: f.set({"styleIndex": arr.indexOf(f.get(field.value))})
                    )
                    step = arr.size().divide(colors.size()).ceil()
                    fc = fc.map(
                        lambda f: f.set(
                            {
                                "style": {
                                    "color": color.value[1:]
                                    + str(hex(int(color_opacity.value * 255)))[
                                        2:
                                    ].zfill(2),
                                    "pointSize": point_size.value,
                                    "pointShape": point_shape.value,
                                    "width": line_width.value,
                                    "lineType": line_type.value,
                                    "fillColor": colors.get(
                                        ee.Number(
                                            ee.Number(f.get("styleIndex")).divide(step)
                                        ).floor()
                                    ),
                                }
                            }
                        )
                    )

                    self.addLayer(
                        fc.style(**{"styleProperty": "style"}),
                        {},
                        f"{new_layer_name.value}",
                    )

                    if (
                        len(palette.value)
                        and legend_chk.value
                        and len(legend_labels.value) > 0
                    ):
                        legend_colors = [
                            color.strip() for color in palette.value.split(",")
                        ]
                        legend_keys = [
                            label.strip() for label in legend_labels.value.split(",")
                        ]
                        self.add_legend(
                            legend_title=legend_title.value,
                            legend_keys=legend_keys,
                            legend_colors=legend_colors,
                            layer_name=new_layer_name.value,
                        )

                compute_label.value = ""

            def close_btn_clicked(b):
                self.remove_control(self.vis_control)
                self.vis_control.close()
                self.vis_widget.close()

                if (
                    self.colorbar_ctrl is not None
                    and self.colorbar_ctrl in self.controls
                ):
                    self.remove_control(self.colorbar_ctrl)
                    self.colorbar_ctrl.close()
                    self.colorbar_widget.close()

            import_btn.on_click(import_btn_clicked)
            apply_btn.on_click(apply_btn_clicked)
            close_btn.on_click(close_btn_clicked)

            vis_widget.children = [
                label,
                new_layer_name,
                widgets.HBox([color, color_opacity, color_opacity_label]),
                widgets.HBox([point_size, point_shape]),
                widgets.HBox([line_width, line_type]),
                widgets.HBox(
                    [fill_color, fill_color_opacity, fill_color_opacity_label]
                ),
                style_vbox,
                widgets.HBox([import_btn, apply_btn, close_btn]),
            ]

            if geometry_type(ee_object) in ["Point", "MultiPoint"]:
                point_size.disabled = False
                point_shape.disabled = False
            else:
                point_size.disabled = True
                point_shape.disabled = True

            return vis_widget

    def add_styled_vector(
        self, ee_object, column, palette, layer_name="Untitled", **kwargs
    ):
        """Adds a styled vector to the map.

        Args:
            ee_object (object): An ee.FeatureCollection.
            column (str): The column name to use for styling.
            palette (list): The palette (e.g., list of colors) to use for styling.
            layer_name (str, optional): The name to be used for the new layer. Defaults to "Untitled".
        """
        styled_vector = vector_styling(ee_object, column, palette, **kwargs)
        self.addLayer(styled_vector.style(**{"styleProperty": "style"}), {}, layer_name)

    def add_shapefile(self, in_shp, style=None, layer_name="Untitled"):
        """Adds a shapefile to the map

        Args:
            in_shp (str): The input file path to the shapefile.
            style (dict, optional): A dictionary specifying the style to be used. Defaults to None.
            layer_name (str, optional): The layer name to be used. Defaults to "Untitled".

        Raises:
            FileNotFoundError: The provided shapefile could not be found.
        """
        if not os.path.exists(in_shp):
            raise FileNotFoundError("The provided shapefile could not be found.")

        data = shp_to_geojson(in_shp)

        if style is None:
            style = {
                "stroke": True,
                "color": "#000000",
                "weight": 2,
                "opacity": 1,
                "fill": True,
                "fillColor": "#000000",
                "fillOpacity": 0.4,
                # "clickable": True,
            }

        geo_json = ipyleaflet.GeoJSON(data=data, style=style, name=layer_name)
        self.add_layer(geo_json)

    def add_geojson(self, in_geojson, style=None, layer_name="Untitled"):
        """Adds a GeoJSON file to the map.

        Args:
            in_geojson (str): The input file path to the GeoJSON.
            style (dict, optional): A dictionary specifying the style to be used. Defaults to None.
            layer_name (str, optional): The layer name to be used.. Defaults to "Untitled".

        Raises:
            FileNotFoundError: The provided GeoJSON file could not be found.
        """
        import json

        if not os.path.exists(in_geojson):
            raise FileNotFoundError("The provided GeoJSON file could not be found.")

        with open(in_geojson) as f:
            data = json.load(f)

        if style is None:
            style = {
                "stroke": True,
                "color": "#000000",
                "weight": 2,
                "opacity": 1,
                "fill": True,
                "fillColor": "#000000",
                "fillOpacity": 0.4,
                # "clickable": True,
            }

        geo_json = ipyleaflet.GeoJSON(data=data, style=style, name=layer_name)
        self.add_layer(geo_json)

    def add_kml(self, in_kml, style=None, layer_name="Untitled"):
        """Adds a GeoJSON file to the map.

        Args:
            in_kml (str): The input file path to the KML.
            style (dict, optional): A dictionary specifying the style to be used. Defaults to None.
            layer_name (str, optional): The layer name to be used.. Defaults to "Untitled".

        Raises:
            FileNotFoundError: The provided KML file could not be found.
        """
        import json

        if not os.path.exists(in_kml):
            raise FileNotFoundError("The provided KML file could not be found.")

        out_json = os.path.join(os.getcwd(), "tmp.geojson")

        kml_to_geojson(in_kml, out_json)

        with open(out_json) as f:
            data = json.load(f)

        if style is None:
            style = {
                "stroke": True,
                "color": "#000000",
                "weight": 2,
                "opacity": 1,
                "fill": True,
                "fillColor": "#000000",
                "fillOpacity": 0.4,
                # "clickable": True,
            }

        geo_json = ipyleaflet.GeoJSON(data=data, style=style, name=layer_name)
        self.add_layer(geo_json)
        os.remove(out_json)


# The functions below are outside the Map class.


def ee_tile_layer(
    ee_object, vis_params={}, name="Layer untitled", shown=True, opacity=1.0
):
    """Converts and Earth Engine layer to ipyleaflet TileLayer.

    Args:
        ee_object (Collection|Feature|Image|MapId): The object to add to the map.
        vis_params (dict, optional): The visualization parameters. Defaults to {}.
        name (str, optional): The name of the layer. Defaults to 'Layer untitled'.
        shown (bool, optional): A flag indicating whether the layer should be on by default. Defaults to True.
        opacity (float, optional): The layer's opacity represented as a number between 0 and 1. Defaults to 1.
    """

    image = None

    if (
        not isinstance(ee_object, ee.Image)
        and not isinstance(ee_object, ee.ImageCollection)
        and not isinstance(ee_object, ee.FeatureCollection)
        and not isinstance(ee_object, ee.Feature)
        and not isinstance(ee_object, ee.Geometry)
    ):
        err_str = "\n\nThe image argument in 'addLayer' function must be an instace of one of ee.Image, ee.Geometry, ee.Feature or ee.FeatureCollection."
        raise AttributeError(err_str)

    if (
        isinstance(ee_object, ee.geometry.Geometry)
        or isinstance(ee_object, ee.feature.Feature)
        or isinstance(ee_object, ee.featurecollection.FeatureCollection)
    ):
        features = ee.FeatureCollection(ee_object)

        width = 2

        if "width" in vis_params:
            width = vis_params["width"]

        color = "000000"

        if "color" in vis_params:
            color = vis_params["color"]

        image_fill = features.style(**{"fillColor": color}).updateMask(
            ee.Image.constant(0.5)
        )
        image_outline = features.style(
            **{"color": color, "fillColor": "00000000", "width": width}
        )

        image = image_fill.blend(image_outline)
    elif isinstance(ee_object, ee.image.Image):
        image = ee_object
    elif isinstance(ee_object, ee.imagecollection.ImageCollection):
        image = ee_object.mosaic()

    map_id_dict = ee.Image(image).getMapId(vis_params)
    tile_layer = TileLayer(
        url=map_id_dict["tile_fetcher"].url_format,
        attribution="Google Earth Engine",
        name=name,
        opacity=opacity,
        visible=shown,
    )
    return tile_layer
