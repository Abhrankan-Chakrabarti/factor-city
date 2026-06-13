import sys
import open3d as o3d
import open3d.visualization.gui as gui
import open3d.visualization.rendering as rendering
import numpy as np

# ---------------------------------------------------------------------------
# Prime color palette (RGB, normalized 0–1)
# ---------------------------------------------------------------------------
PRIME_COLORS = {
    2:  [0.90, 0.10, 0.10],   # Red
    3:  [0.10, 0.30, 0.90],   # Blue
    5:  [0.10, 0.70, 0.20],   # Green
    7:  [0.90, 0.80, 0.10],   # Yellow
    11: [0.90, 0.50, 0.10],   # Orange
    13: [0.60, 0.10, 0.80],   # Purple
    17: [0.10, 0.80, 0.85],   # Cyan
    19: [0.85, 0.10, 0.60],   # Magenta
    23: [0.40, 0.80, 0.40],   # Lime
    29: [0.80, 0.40, 0.20],   # Sienna
    31: [0.20, 0.40, 0.80],   # Steel blue
}
DEFAULT_COLOR = [0.55, 0.55, 0.55]   # Gray — primes > 31

BLOCK_SIZE   = 1.0
BLOCK_HEIGHT = 0.5
GAP          = 0.1

INITIAL_GRID = [
    [30,  42,  66,  78],    # 2·3·5 / 2·3·7 / 2·3·11 / 2·3·13
    [12,  18,  20,  28],    # 2²·3  / 2·3²  / 2²·5   / 2²·7
    [8,   27,  25,  49],    # 2³    / 3³    / 5²      / 7²
    [6,   10,  15,  35],    # 2·3   / 2·5   / 3·5     / 5·7
    [2,   3,   5,   7],     # single-floor prime baseline
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_prime_factors(n: int) -> list[int]:
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


def create_block(col: int, row: int, level: int, color: list) -> o3d.geometry.TriangleMesh:
    w = BLOCK_SIZE   * (1 - GAP)
    h = BLOCK_HEIGHT * (1 - GAP)
    d = BLOCK_SIZE   * (1 - GAP)
    mesh = o3d.geometry.TriangleMesh.create_box(width=w, height=h, depth=d)
    mesh.compute_vertex_normals()
    offset_x = col   * BLOCK_SIZE   + GAP / 2
    offset_y = level * BLOCK_HEIGHT + GAP / 2
    offset_z = row   * BLOCK_SIZE   + GAP / 2
    mesh.translate(np.array([offset_x, offset_y, offset_z]))
    mesh.paint_uniform_color(color)
    return mesh


def ray_aabb_intersect(ray_o: np.ndarray, ray_d: np.ndarray,
                       aabb_min: np.ndarray, aabb_max: np.ndarray) -> float:
    """Slab method ray-AABB intersection. Returns t > 0 on hit, else inf."""
    with np.errstate(divide='ignore', invalid='ignore'):
        t1 = (aabb_min - ray_o) / ray_d
        t2 = (aabb_max - ray_o) / ray_d
    tmin = np.minimum(t1, t2).max()
    tmax = np.maximum(t1, t2).min()
    if tmax >= max(tmin, 0.0):
        return tmin if tmin >= 0 else tmax
    return float('inf')


# ---------------------------------------------------------------------------
# Dynamic Factor City Application
# ---------------------------------------------------------------------------

class FactorCityApp:
    def __init__(self, grid: list[list[int]]):
        self.grid          = [row[:] for row in grid]
        self.is_animating  = True
        self.truck_speed   = 1.0
        self.time_state    = 0.0
        self.selected_building: tuple | None = None

        self.building_geom_names: list[str]  = []
        self.labels_3d:           list       = []   # gui.Label3D handles

        gui.Application.instance.initialize()
        self.window = gui.Application.instance.create_window(
            "Factor City Lab — Ultimate Prime Explorer", 1400, 800
        )

        self.scene_widget = gui.SceneWidget()
        self.scene_widget.scene = rendering.Open3DScene(self.window.renderer)
        self.scene_widget.scene.set_background([0.08, 0.08, 0.12, 1.0])

        em = self.window.theme.font_size
        self.panel = gui.Vert(
            0.5 * em, gui.Margins(0.5 * em, 0.5 * em, 0.5 * em, 0.5 * em)
        )

        self.mat = rendering.MaterialRecord()
        self.mat.shader = "defaultLit"

        self.setup_ui_controls(em)
        self.window.add_child(self.scene_widget)
        self.window.add_child(self.panel)

        self.build_city_objects()
        self.build_static_legend()
        self.build_delivery_truck()

        bounds = self.scene_widget.scene.bounding_box
        self.scene_widget.setup_camera(60, bounds, bounds.get_center())

        self.window.set_on_layout(self.on_layout)
        self.scene_widget.set_on_mouse(self.on_scene_mouse_click)
        self.scene_widget.set_on_key(self.on_key)
        gui.Application.instance.post_to_main_thread(self.window, self.animation_loop)

    # -----------------------------------------------------------------------
    # UI setup
    # -----------------------------------------------------------------------

    def setup_ui_controls(self, em: float) -> None:
        self.panel.add_child(gui.Label("FACTOR CITY ENGINE"))
        self.panel.add_child(gui.Label(""))

        self.label_cb = gui.Checkbox("Show Equation Labels")
        self.label_cb.checked = True
        self.label_cb.set_on_checked(self.toggle_labels)
        self.panel.add_child(self.label_cb)

        self.anim_cb = gui.Checkbox("Run Delivery Truck")
        self.anim_cb.checked = True
        self.anim_cb.set_on_checked(self.toggle_animation)
        self.panel.add_child(self.anim_cb)

        self.panel.add_child(gui.Label("Truck Speed:"))
        self.speed_slider = gui.Slider(gui.Slider.DOUBLE)
        self.speed_slider.set_limits(0.1, 3.0)
        self.speed_slider.double_value = 1.0
        self.speed_slider.set_on_value_changed(self.change_speed)
        self.panel.add_child(self.speed_slider)

        self.panel.add_child(gui.Label(""))
        self.panel.add_child(gui.Label("BUILDING INSPECTOR:"))
        self.inspector_label = gui.Label("Click a building to analyze...")
        self.panel.add_child(self.inspector_label)

        self.panel.add_child(gui.Label(""))
        self.panel.add_child(gui.Label("Custom Block Tower:"))

        input_row = gui.Horiz(0.25 * em)
        self.num_input = gui.NumberEdit(gui.NumberEdit.INT)
        self.num_input.int_value = 24
        input_row.add_child(self.num_input)

        btn = gui.Button("Deploy")
        btn.set_on_clicked(self.deploy_custom_tower)
        input_row.add_child(btn)
        self.panel.add_child(input_row)

        self.panel.add_child(gui.Label(""))
        self.panel.add_child(gui.Label("PRIME LEGEND:"))
        color_names = {
            2:"Red", 3:"Blue", 5:"Green", 7:"Yellow", 11:"Orange",
            13:"Purple", 17:"Cyan", 19:"Magenta", 23:"Lime",
            29:"Sienna", 31:"Steel blue"
        }
        for p in sorted(PRIME_COLORS.keys()):
            self.panel.add_child(gui.Label(f"  p={p:2d}  {color_names.get(p, 'Gray')}"))

    # -----------------------------------------------------------------------
    # Scene construction
    # -----------------------------------------------------------------------

    def _clear_labels(self) -> None:
        for lbl in self.labels_3d:
            self.scene_widget.remove_3d_label(lbl)
        self.labels_3d.clear()

    def build_city_objects(self) -> None:
        for name in self.building_geom_names:
            self.scene_widget.scene.remove_geometry(name)
        self.building_geom_names.clear()
        self._clear_labels()

        show = self.label_cb.checked if hasattr(self, 'label_cb') else True

        for row_idx, row in enumerate(self.grid):
            for col_idx, number in enumerate(row):
                if number <= 1:
                    continue

                factors = get_prime_factors(number)

                for level, prime in enumerate(factors):
                    color = PRIME_COLORS.get(prime, DEFAULT_COLOR)
                    if self.selected_building == (row_idx, col_idx):
                        color = [min(1.0, c + 0.25) for c in color]
                    block = create_block(col_idx, row_idx, level, color)
                    name  = f"block_{row_idx}_{col_idx}_{level}"
                    self.scene_widget.scene.add_geometry(name, block, self.mat)
                    self.building_geom_names.append(name)

                if show:
                    top_y    = len(factors) * BLOCK_HEIGHT + 0.3
                    center_x = col_idx * BLOCK_SIZE + BLOCK_SIZE / 2
                    center_z = row_idx * BLOCK_SIZE + BLOCK_SIZE / 2
                    factor_str = " x ".join(map(str, factors))
                    lbl = self.scene_widget.add_3d_label(
                        np.array([center_x, top_y, center_z]),
                        f"{number}={factor_str}"
                    )
                    self.labels_3d.append(lbl)

    def build_static_legend(self) -> None:
        x_start = len(self.grid[0]) * BLOCK_SIZE + 1.0
        for idx, p in enumerate(sorted(PRIME_COLORS.keys())):
            cube = o3d.geometry.TriangleMesh.create_box(0.4, 0.4, 0.4)
            cube.compute_vertex_normals()
            cube.translate(np.array([x_start, 0.0, idx * 0.6]))
            cube.paint_uniform_color(PRIME_COLORS[p])
            self.scene_widget.scene.add_geometry(f"legend_{p}", cube, self.mat)

    def build_delivery_truck(self) -> None:
        self.truck_mesh = o3d.geometry.TriangleMesh.create_sphere(radius=0.18)
        self.truck_mesh.compute_vertex_normals()
        self.truck_mesh.paint_uniform_color([1.0, 1.0, 1.0])
        self.scene_widget.scene.add_geometry("delivery_truck", self.truck_mesh, self.mat)

    # -----------------------------------------------------------------------
    # Building AABBs for manual ray picking
    # -----------------------------------------------------------------------

    def _building_aabbs(self) -> list[tuple]:
        """Returns list of (row, col, aabb_min, aabb_max) for each building."""
        aabbs = []
        for row_idx, row in enumerate(self.grid):
            for col_idx, number in enumerate(row):
                if number <= 1:
                    continue
                factors = get_prime_factors(number)
                floors  = len(factors)
                bmin = np.array([
                    col_idx * BLOCK_SIZE,
                    0.0,
                    row_idx * BLOCK_SIZE,
                ])
                bmax = np.array([
                    col_idx * BLOCK_SIZE + BLOCK_SIZE,
                    floors  * BLOCK_HEIGHT,
                    row_idx * BLOCK_SIZE + BLOCK_SIZE,
                ])
                aabbs.append((row_idx, col_idx, bmin, bmax))
        return aabbs

    # -----------------------------------------------------------------------
    # UI event callbacks
    # -----------------------------------------------------------------------

    def toggle_labels(self, checked: bool) -> None:
        self.build_city_objects()
        self.scene_widget.force_redraw()

    def toggle_animation(self, checked: bool) -> None:
        self.is_animating = checked

    def change_speed(self, value: float) -> None:
        self.truck_speed = value

    def deploy_custom_tower(self) -> None:
        val = int(self.num_input.int_value)
        if val <= 1:
            return

        inserted = False
        for r in range(len(self.grid)):
            for c in range(len(self.grid[0])):
                if self.grid[r][c] <= 1:
                    self.grid[r][c] = val
                    inserted = True
                    break
            if inserted:
                break

        if not inserted:
            self.grid[0][0] = val

        self.build_city_objects()
        self.scene_widget.force_redraw()

    # -----------------------------------------------------------------------
    # Manual ray-AABB picking
    # -----------------------------------------------------------------------

    def on_key(self, event: gui.KeyEvent) -> int:
        if (event.type == gui.KeyEvent.Type.DOWN
                and event.key == gui.KeyName.Q):
            gui.Application.instance.quit()
            return gui.SceneWidget.EventCallbackResult.HANDLED
        return gui.SceneWidget.EventCallbackResult.IGNORED

    def on_scene_mouse_click(self, event: gui.MouseEvent) -> int:
        if (event.type == gui.MouseEvent.Type.BUTTON_DOWN
                and event.is_button_down(gui.MouseButton.LEFT)):

            frame  = self.scene_widget.frame
            vp_x   = event.x - frame.x
            vp_y   = event.y - frame.y
            camera = self.scene_widget.scene.camera

            # Use camera.unproject() to get world-space ray points at near/far
            world_near = np.array(camera.unproject(
                vp_x, vp_y, 0.0, frame.width, frame.height
            ))
            world_mid = np.array(camera.unproject(
                vp_x, vp_y, 0.01, frame.width, frame.height
            ))

            ray_o = world_near
            ray_d = world_mid - world_near
            norm  = np.linalg.norm(ray_d)
            print(f"[PICK] vp=({vp_x:.0f},{vp_y:.0f}) near={np.round(world_near,2)} mid={np.round(world_mid,2)} |ray|={norm:.4f}")
            if norm < 1e-10:
                return gui.SceneWidget.EventCallbackResult.IGNORED
            ray_d /= norm

            # Test against all building AABBs
            best_t   = float('inf')
            best_hit = None
            for (r, c, bmin, bmax) in self._building_aabbs():
                t = ray_aabb_intersect(ray_o, ray_d, bmin, bmax)
                print(f"  AABB ({r},{c}) t={t:.3f}")
                if t < best_t:
                    best_t   = t
                    best_hit = (r, c)
            print(f"  best_hit={best_hit} best_t={best_t:.3f}")

            if best_hit is not None:
                r, c    = best_hit
                number  = self.grid[r][c]
                factors = get_prime_factors(number)
                factor_str = " x ".join(map(str, factors))
                unique_p   = sorted(set(factors))
                info = (
                    f"Number : {number}\n"
                    f"Factors: {factor_str}\n"
                    f"Primes : {', '.join(map(str, unique_p))}\n"
                    f"Floors : {len(factors)}\n"
                    f"Grid   : row {r}, col {c}"
                )
                self.selected_building = (r, c)
                self.inspector_label.text = info
                self.build_city_objects()
                self.scene_widget.force_redraw()

            return gui.SceneWidget.EventCallbackResult.HANDLED

        return gui.SceneWidget.EventCallbackResult.IGNORED

    # -----------------------------------------------------------------------
    # Layout & animation
    # -----------------------------------------------------------------------

    def on_layout(self, layout_context) -> None:
        r = self.window.content_rect
        self.panel.frame        = gui.Rect(r.x, r.y, 300, r.height)
        self.scene_widget.frame = gui.Rect(r.x + 300, r.y, r.width - 300, r.height)

    def animation_loop(self) -> None:
        if not self.window.is_visible:
            return

        if self.is_animating:
            self.time_state += 0.02 * self.truck_speed
            t     = self.time_state
            max_x = len(self.grid[0])
            max_z = len(self.grid)

            new_x = max_x / 2 + np.sin(t) * (max_x / 2 - 0.5)
            new_z = max_z / 2 + np.cos(t) * (max_z / 2 - 0.5)
            new_y = 0.15 + abs(np.sin(t * 3)) * 0.35

            T       = np.eye(4)
            T[0, 3] = new_x
            T[1, 3] = new_y
            T[2, 3] = new_z
            self.scene_widget.scene.set_geometry_transform("delivery_truck", T)
            self.scene_widget.force_redraw()

        gui.Application.instance.post_to_main_thread(self.window, self.animation_loop)

    def run(self) -> None:
        gui.Application.instance.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = FactorCityApp(INITIAL_GRID)
    app.run()