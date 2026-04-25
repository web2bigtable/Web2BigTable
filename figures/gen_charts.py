"""Generate benchmark charts for README."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

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

# ── Per-model colors (matching LaTeX acblue/accoral/acteal/acamber/acpurple) ──
CORAL   = "#c04b30"   # accoral  RGB(192,75,48)   — o3-high
TEAL    = "#1d9e75"   # acteal   RGB(29,158,117)  — Gemini 2.5 Pro
PURPLE  = "#644aa6"   # acpurple RGB(100,74,166)  — Claude Sonnet 4
AMBER   = "#ba7517"   # acamber  RGB(186,117,23)  — Doubao-1.6
BLUE    = "#1f4e79"   # acblue   RGB(31,78,121)   — Ours


# ══════════════════════════════════════════════════════════════
# 1. WideSearch scatter chart
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 8))

# (name, row_f1, item_f1, sr, marker, color)
baselines = [
    ("o3-high",         37.80, 57.30, 5.1, "D",        CORAL),
    ("Gemini 2.5 Pro",  33.50, 57.40, 2.0, "^",        TEAL),
    ("Claude Sonnet 4", 38.50, 62.20, 3.6, "s",        PURPLE),
    ("Doubao-1.6",      34.00, 54.60, 2.5, "$\\oplus$", AMBER),
]
ours = ("Web2BigTable (Ours)", 63.53, 80.12, 38.5)

# Label offsets in data coords: (x, y, ha, va) matching TikZ node positions
label_pos = {
    "o3-high":         (39.5, 57.30, "left",  "center"),
    "Gemini 2.5 Pro":  (33.50, 58.5, "left",  "bottom"),
    "Claude Sonnet 4": (40.2, 62.20, "left",  "center"),
    "Doubao-1.6":      (35.8, 54.60, "left",  "center"),
}

for name, rf1, if1, sr, marker, color in baselines:
    size = 260 if marker == "$\\oplus$" else 200
    ax.scatter(rf1, if1, s=size, c=color, alpha=0.45,
               edgecolors=color, linewidths=1.5, zorder=5,
               marker=marker)
    lx, ly, ha, va = label_pos[name]
    ax.text(lx, ly, f"{name} (SR {sr})", ha=ha, va=va,
            fontsize=12, color=color)

# Ours — large circle with SR label inside, name above
ax.scatter(ours[1], ours[2], s=2800, c=BLUE, alpha=0.55,
           edgecolors=BLUE, linewidths=2, zorder=4)
ax.text(ours[1], ours[2], f"(SR {ours[3]})",
        ha="center", va="center", fontsize=11, fontweight="bold",
        color="white", zorder=6)
ax.text(ours[1], 84.5, f"{ours[0]} (SR {ours[3]})",
        ha="center", va="bottom", fontsize=13, fontweight="bold", color=BLUE)

ax.set_xlabel("Row F1 (Avg@4)", fontsize=14, labelpad=10)
ax.set_ylabel("Item F1 (Avg@4)", fontsize=14, labelpad=10)
ax.set_xlim(26, 74)
ax.set_ylim(48, 90)
ax.set_xticks([30, 40, 50, 60, 70])
ax.set_yticks([50, 55, 60, 65, 70, 75, 80, 85])

fig.tight_layout()
fig.savefig("figures/widesearch.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("figures/widesearch.png")


# ══════════════════════════════════════════════════════════════
# 2. XBench-DeepSearch horizontal bar chart
# ══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 7.5))

# Bottom → top, matching TikZ y=1..10
models = [
    "WebDancer", "WebSailor", "OAgents", "WebShaper", "Gemini-2.5",
    "DeepMiner", "Claude-4.5", "Kimi-Res.", "Minimax-M2", "Web2BigTable (Ours)",
]
scores = [40.0, 53.3, 54.5, 54.6, 56.0, 62.0, 66.0, 69.0, 72.0, 73.0]
ours_idx = 9

BAR_GRAY = "#bdbdbd"
bar_xmin = 30  # bars start from here

for i, (model, score) in enumerate(zip(models, scores)):
    is_ours = (i == ours_idx)
    color = BLUE if is_ours else BAR_GRAY
    alpha = 0.7 if is_ours else 0.4
    edge = BLUE if is_ours else "#9e9e9e"
    lw = 0.6 if is_ours else 0.4
    ax.barh(i + 1, score - bar_xmin, left=bar_xmin, height=0.6,
            color=color, alpha=alpha, edgecolor=edge, linewidth=lw, zorder=3)
    txt_color = BLUE if is_ours else "#6b7280"
    weight = "bold" if is_ours else "normal"
    ax.text(score + 0.4, i + 1, f"{score:.1f}", va="center", ha="left",
            fontsize=11, color=txt_color, fontweight=weight)

ax.set_yticks(range(1, len(models) + 1))
ax.set_yticklabels(models, fontsize=11)
labels = ax.get_yticklabels()
labels[ours_idx].set_fontweight("bold")
labels[ours_idx].set_color(BLUE)

ax.set_xlabel("Accuracy", fontsize=13, labelpad=10)
ax.set_xlim(bar_xmin, 80)
ax.set_ylim(0.2, 10.8)
ax.set_xticks([30, 40, 50, 60, 70, 80])

fig.tight_layout()
fig.savefig("figures/xbench_deepsearch.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("figures/xbench_deepsearch.png")
