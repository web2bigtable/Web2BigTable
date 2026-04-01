"""Generate benchmark charts for README."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Shared style ──────────────────────────────────────────────
BG = "#ffffff"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "axes.facecolor": BG,
    "figure.facecolor": BG,
    "axes.edgecolor": "#e5e7eb",
    "axes.grid": True,
    "grid.color": "#f0f0f0",
    "grid.linewidth": 0.5,
    "xtick.color": "#6b7280",
    "ytick.color": "#6b7280",
    "text.color": "#111827",
})

# ── Per-model colors (matching LaTeX) ────────────────────────
CORAL   = "#e06050"   # o3-high
TEAL    = "#20a0a0"   # Gemini 2.5 Pro
PURPLE  = "#8060c0"   # Claude Sonnet 4
AMBER   = "#d09020"   # Doubao-1.6
BLUE    = "#005a9c"   # Ours


# ══════════════════════════════════════════════════════════════
# 1. WideSearch-EN scatter chart
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 10))

# Data: (name, row_f1, item_f1, sr, marker, color)
baselines = [
    ("o3-high",          37.80, 57.30, 5.1, "D", CORAL),
    ("Gemini 2.5 Pro",   36.60, 59.10, 4.3, "^", TEAL),
    ("Claude Sonnet 4",  38.50, 62.20, 3.6, "s", PURPLE),
    ("Doubao-1.6",       34.00, 54.60, 2.5, "P", AMBER),   # plus (filled)
]
ours = ("Memento-Team (Ours)", 63.53, 80.12, 38.5)

# Label positions: (dx, dy, ha)
label_pos = {
    "o3-high":          (12,  0, "left"),
    "Gemini 2.5 Pro":   (-12, 6, "right"),
    "Claude Sonnet 4":  (12,  0, "left"),
    "Doubao-1.6":       (-12, -6, "right"),
}

# Plot baselines
for name, rf1, if1, sr, marker, color in baselines:
    ax.scatter(rf1, if1, s=200, c=color, alpha=0.45,
               edgecolors=color, linewidths=1.5, zorder=5,
               marker=marker)
    dx, dy, ha = label_pos[name]
    ax.annotate(f"{name} (SR {sr})", (rf1, if1),
                textcoords="offset points", xytext=(dx, dy),
                ha=ha, va="center", fontsize=12, color=color)

# Plot ours — large circle with SR inside
ax.scatter(ours[1], ours[2], s=2800, c=BLUE, alpha=0.2,
           edgecolors=BLUE, linewidths=2, zorder=4)
ax.annotate(f"{ours[0]} (SR {ours[3]})", (ours[1], ours[2]),
            textcoords="offset points", xytext=(0, 38),
            ha="center", fontsize=14, fontweight="bold", color=BLUE)

# Single-agent reference lines (dashed)
ref_lines = [
    ("Gemini-3-Pro",       57.0, TEAL),
    ("GPT-5 High",         62.2, CORAL),
    ("Seed1.8",            63.8, AMBER),
    ("Claude-4.5-Sonnet",  65.7, PURPLE),
]
# Stagger label x positions and y anchors to avoid overlap
label_x = [58, 44, 58, 44]
anchor_y = ["south", "north", "south", "south"]

for (name, val, color), lx, ay in zip(ref_lines, label_x, anchor_y):
    ax.axhline(y=val, color=color, alpha=0.35, linewidth=1, linestyle="--", zorder=2)
    y_off = 0.4 if ay == "south" else -0.4
    va = "bottom" if ay == "south" else "top"
    ax.text(lx, val + y_off, f"{name}: {val}", fontsize=10, color=color, alpha=0.7, va=va)

ax.set_xlabel("Row F1 (Avg@4)", fontsize=14, labelpad=10)
ax.set_ylabel("Item F1 (Avg@4)", fontsize=14, labelpad=10)
ax.set_xlim(26, 74)
ax.set_ylim(46, 90)
ax.set_xticks([30, 40, 50, 60, 70])
ax.set_yticks([50, 55, 60, 65, 70, 75, 80, 85])
ax.set_title("WideSearch-EN", fontsize=18, fontweight="bold", pad=16)

fig.tight_layout()
fig.savefig("figures/widesearch_en.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("figures/widesearch_en.png")


# ══════════════════════════════════════════════════════════════
# 2. XBench-DeepSearch horizontal bar chart
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 9))

models = [
    "GLM-4.5", "Kimi-Res.", "Memento-Team (Ours)",
    "Claude-4.5", "DeepMiner", "Gemini-2.5",
    "WebShaper", "OAgents", "WebSailor", "WebDancer",
]
scores = [70.0, 69.0, 68.0, 66.0, 62.0, 56.0, 54.6, 54.5, 53.3, 40.0]
ours_idx = 2  # "Memento-Team (Ours)"

BAR_GRAY = "#bdbdbd"
bar_xmin = 35  # bars start from here

for i, (model, score) in enumerate(zip(models, scores)):
    is_ours = (i == ours_idx)
    color = BLUE if is_ours else BAR_GRAY
    alpha = 0.7 if is_ours else 0.4
    edge = BLUE if is_ours else (BAR_GRAY + "B3")
    ax.barh(i, score - bar_xmin, left=bar_xmin, height=0.6,
            color=color, alpha=alpha, edgecolor=edge, linewidth=0.5, zorder=3)
    # Value label
    txt_color = BLUE if is_ours else "#6b7280"
    weight = "bold" if is_ours else "normal"
    ax.text(score + 0.5, i, f"{score:.1f}", va="center", ha="left",
            fontsize=12, color=txt_color, fontweight=weight)

ax.set_yticks(range(len(models)))
ax.set_yticklabels(models, fontsize=12)
# Bold "Ours" label
labels = ax.get_yticklabels()
labels[ours_idx].set_fontweight("bold")
labels[ours_idx].set_color(BLUE)

ax.set_xlabel("Accuracy", fontsize=14, labelpad=10)
ax.set_xlim(bar_xmin, 78)
ax.set_xticks([40, 50, 60, 70])
ax.set_title("XBench-DeepSearch", fontsize=18, fontweight="bold", pad=16)
ax.invert_yaxis()

fig.tight_layout()
fig.savefig("figures/xbench_deepsearch.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("figures/xbench_deepsearch.png")
