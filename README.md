# Factor City

An interactive 3D prime factorization visualizer built with **Open3D** and **NumPy**. Each integer in a configurable grid is rendered as a tower of colored blocks — one floor per prime factor (with multiplicity), where each prime has a distinct color. The result is a miniature city whose skyline encodes the arithmetic structure of its buildings.

## Prerequisites

This script requires **Python 3.10+** and the following packages:

### Installation

```bash
pip install open3d numpy
```

## Usage

```bash
python factor_city.py
```

No command-line arguments are needed. The application opens a 1400×800 interactive window with a side control panel.

## How It Works

**Factorization → Architecture**

Each number in `INITIAL_GRID` is decomposed into its prime factors with multiplicity using trial division. For example:

```
30 = 2 × 3 × 5   →   3-floor tower: Red / Blue / Green
12 = 2 × 2 × 3   →   3-floor tower: Red / Red / Blue
 7 = 7            →   1-floor tower: Yellow
```

Building **height** encodes the number of prime factors (Ω(n)), and **color** encodes which prime occupies each floor, making the multiplicative structure of every number immediately visible at a glance.

**Prime Color Palette**

| Prime | Color      | Prime | Color      |
|-------|------------|-------|------------|
| 2     | Red        | 17    | Cyan       |
| 3     | Blue       | 19    | Magenta    |
| 5     | Green      | 23    | Lime       |
| 7     | Yellow     | 29    | Sienna     |
| 11    | Orange     | 31    | Steel blue |
| 13    | Purple     | >31   | Gray       |

A color-coded legend is rendered to the right of the city grid in the 3D scene.

**Animated Delivery Truck**

A white sphere orbits the city along a sinusoidal path with a hopping vertical motion, driven by an `animation_loop` that reschedules itself each frame via `post_to_main_thread`.

## Control Panel

| Control | Description |
|---------|-------------|
| Render 3D Equations | Toggle floating `n = p₁ × p₂ × …` labels above each rooftop |
| Run Delivery Truck | Pause or resume the animated truck |
| Truck Speed | Slider — adjusts animation speed from 0.1× to 3.0× |
| Building Inspector | Displays factorization details for the last clicked building |
| Construct Custom Block Tower | Enter any integer ≥ 2 and click **Deploy** to place it in the next empty grid slot |

## Building Inspector

Left-clicking any block in the scene triggers a raycast pick. The side panel updates with:

```
Number : 30
Factors: 2 × 3 × 5
Primes : 2, 3, 5
Floors : 3
Grid   : row 0, col 0
```

The selected building is highlighted by brightening its block colors.

## Customizing the Grid

Edit `INITIAL_GRID` at the top of the script. Any 2D list of integers works — numbers ≤ 1 are treated as empty lots. The grid can be any rectangular shape.

```python
INITIAL_GRID = [
    [30,  42,  66,  78],
    [12,  18,  20,  28],
    [8,   27,  25,  49],
    [6,   10,  15,  35],
    [2,   3,   5,   7],
]
```

Block dimensions and spacing are controlled by three constants:

```python
BLOCK_SIZE   = 1.0   # footprint (X and Z)
BLOCK_HEIGHT = 0.5   # height per floor (Y)
GAP          = 0.1   # gap fraction between blocks
```

## Scene Navigation

| Action | Control |
|--------|---------|
| Rotate | Left-click + drag |
| Pan    | Right-click + drag |
| Zoom   | Scroll wheel |
| Quit   | Q or close window |

