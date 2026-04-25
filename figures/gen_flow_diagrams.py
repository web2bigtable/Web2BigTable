"""Generate training and inference flow diagrams for README."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "mathtext.fontset": "cm",
    "mathtext.default": "regular",
})

# ── Colors (approx xcolor mixes used in the TikZ source) ─────────
S1_FILL, S1_EDGE = "#fff5cc", "#9e8a1a"   # yellow!15 / yellow!55!black
S2_FILL, S2_EDGE = "#e3e6ec", "#5a5a5a"   # blue!8!gray!15 / gray!65!black
S3_FILL, S3_EDGE = "#fcdbdb", "#a83232"   # red!10 / red!55!black
ME_FILL, ME_EDGE = "#dcf2dc", "#2e7d32"   # green!10 / green!55!black
MB_FILL, MB_EDGE = "#fde0c2", "#b96b00"   # orange!18 / orange!80!black
LINK_R = "#9e7e1a"   # link1 (read from S1, yellow!60!black)
LINK_G = "#5a5a5a"   # link2 (gray!65!black)
LINK_W = "#a83232"   # link3 (write from S3, red!55!black)
SEP_C  = "#a8a8a8"


def box(ax, cx, cy, w, h, fill, edge, lw=1.0):
    p = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.0,rounding_size=0.10",
        facecolor=fill, edgecolor=edge, linewidth=lw, zorder=2,
    )
    ax.add_patch(p)


def arrow(ax, p1, p2, color="black", lw=1.4, ls="-", mutation=14):
    a = FancyArrowPatch(
        p1, p2, arrowstyle="-|>", mutation_scale=mutation,
        color=color, linewidth=lw, linestyle=ls,
        shrinkA=0, shrinkB=0, zorder=4,
    )
    ax.add_patch(a)


def polyline(ax, pts, color="black", lw=1.4, ls="-", with_arrow=True):
    if len(pts) < 2:
        return
    if with_arrow:
        if len(pts) > 2:
            xs = [p[0] for p in pts[:-1]]
            ys = [p[1] for p in pts[:-1]]
            ax.plot(xs, ys, color=color, linewidth=lw, linestyle=ls,
                    zorder=4, solid_capstyle="butt", dash_capstyle="butt")
        arrow(ax, pts[-2], pts[-1], color=color, lw=lw, ls=ls)
    else:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=lw, linestyle=ls,
                zorder=4, solid_capstyle="butt", dash_capstyle="butt")


def t(ax, x, y, s, fs=9, w="normal", style="normal", color="black",
      ha="center", va="center"):
    ax.text(x, y, s, ha=ha, va=va, fontsize=fs, fontweight=w,
            fontstyle=style, color=color, zorder=5)


# ══════════════════════════════════════════════════════════════
# 1. Training (self-evolving) flow
# ══════════════════════════════════════════════════════════════
def make_training():
    fig, ax = plt.subplots(figsize=(15.5, 8.2))
    ax.set_xlim(-4.6, 14.2)
    ax.set_ylim(-5.0, 4.6)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Stage boxes ─────────────────────────────────────────
    SW, SH = 3.4, 1.6
    box(ax, 0,   0, SW, SH, S1_FILL, S1_EDGE)
    box(ax, 4.5, 0, SW, SH, S2_FILL, S2_EDGE)
    box(ax, 9.0, 0, SW, SH, S3_FILL, S3_EDGE)

    # Stage 1 text
    t(ax, 0,  0.42, "Stage 1: Orchestrate", fs=10.5, w="bold")
    t(ax, 0,  0.05, "Decompose task", fs=9)
    t(ax, 0, -0.42,
      r"$\mathbf{\tau}\sim\pi_o(\cdot\mid q_k,\mathcal{S}_o^k)$", fs=8.8)

    # Stage 2 text
    t(ax, 4.5,  0.42, "Stage 2: Execute", fs=10.5, w="bold")
    t(ax, 4.5,  0.05, "Parallel worker loop", fs=9)
    t(ax, 4.5, -0.42,
      r"$x_i^{t+1}\sim\pi_w^{(i)}(\cdot\mid\tau_i, m_e^t, s_i)$", fs=8.8)

    # Stage 3 text
    t(ax, 9.0,  0.50, "Stage 3: Evolve", fs=10.5, w="bold")
    t(ax, 9.0,  0.10,
      r"$U(X_k)=\mathrm{Item\!-\!F1}(X_k, X_k^{\mathrm{gold}})$", fs=8.0)
    t(ax, 9.0, -0.40, "reflect and update skills", fs=9)

    # ── Top memories ────────────────────────────────────────
    MW, MH = 3.0, 1.3
    box(ax, 0,   2.4, MW, MH, MB_FILL, MB_EDGE)
    t(ax, 0, 2.7, r"Orch. Skill Bank $\mathcal{S}_o$", fs=9.5, w="bold")
    t(ax, 0, 2.20,
      r"$\mathcal{S}_o^{k+1}=\mathcal{M}_o(\mathcal{S}_o^k, r_o^{k+1})$", fs=8)

    box(ax, 4.5, 2.4, SW, MH, MB_FILL, MB_EDGE)  # match S2 width
    t(ax, 4.5, 2.7, r"Worker Skill Bank $\mathcal{S}_w$", fs=9.5, w="bold")
    t(ax, 4.5, 2.20,
      r"$\mathcal{S}_w^{k+1}=\mathcal{M}_w(\mathcal{S}_w^k, r_o^{k+1})$", fs=8)

    # ── Bottom memory ───────────────────────────────────────
    box(ax, 4.5, -2.1, MW, MH, ME_FILL, ME_EDGE)
    t(ax, 4.5, -1.85, r"Workboard $m_e$", fs=9.5, w="bold")
    t(ax, 4.5, -2.35,
      r"$m_e^{t+1}=\mathcal{M}_e(m_e^t, \{h_i^{t+1}\}_i)$", fs=8)

    # ── Inputs (left column) ────────────────────────────────
    in_x = -2.9
    t(ax, in_x,  0.20, "Training Queries", fs=10.5, w="bold")
    t(ax, in_x, -0.25, r"$\{q_k\}_{k=0}^{K-1}$", fs=10)
    t(ax, in_x, -1.55, "Ground Truth", fs=10.5, w="bold")
    t(ax, in_x, -2.00, r"$\{X_k^{\mathrm{gold}}\}_{k=0}^{K-1}$", fs=10)

    # ── Output (right column) ───────────────────────────────
    out_x = 12.5
    t(ax, out_x,  0.20, "Evolved Skill Banks", fs=10.5, w="bold")
    t(ax, out_x, -0.25, r"$\mathcal{S}_o^{*},\,\mathcal{S}_w^{*}$", fs=10)

    # ── Phase separators (dashed vertical) ──────────────────
    sepL = -1.65
    sepR = 10.95
    ax.plot([sepL, sepL], [-4.3, 4.0], ls="--", color=SEP_C, lw=0.8, zorder=1)
    ax.plot([sepR, sepR], [-4.3, 4.0], ls="--", color=SEP_C, lw=0.8, zorder=1)

    # ── Phase labels ────────────────────────────────────────
    t(ax, in_x, -4.05, "Input",         fs=10.5, w="bold")
    t(ax, 4.5,  -4.05, "Training phase",fs=10.5, w="bold")
    t(ax, out_x,-4.05, "Output",        fs=10.5, w="bold")

    # ── Main horizontal flow ────────────────────────────────
    arrow(ax, (in_x + 0.95, 0), (-SW / 2, 0), lw=1.6)
    arrow(ax, (SW / 2, 0), (4.5 - SW / 2, 0), lw=1.6)
    t(ax, 2.25, 0.22, r"$\mathbf{\tau}$", fs=9, style="italic")
    arrow(ax, (4.5 + SW / 2, 0), (9.0 - SW / 2, 0), lw=1.6)
    t(ax, 6.75, 0.22, r"$X_k$", fs=9, style="italic")

    # ── Episode loop (S3 south-left → bottom rail → S1 south) ─
    polyline(ax, [(9.0 - 0.4, -SH / 2), (8.6, -3.05),
                  (0, -3.05), (0, -SH / 2)], lw=1.4)
    t(ax, 4.5, -2.85, r"next training episode $k\!+\!1$",
      fs=8.5, style="italic")

    # ── Ground-truth routing (down → right → up into S3) ───
    polyline(ax, [(in_x, -2.30), (in_x, -3.62),
                  (9.4, -3.62), (9.4, -SH / 2)], lw=1.4)

    # ── Top memory reads (vertical, dashed) ─────────────────
    arrow(ax, (0, 2.4 - MH / 2), (0, SH / 2),
          color=LINK_R, ls="--", lw=1.2)
    t(ax, 0.18, 1.50, "read", fs=8, style="italic", ha="left")
    arrow(ax, (4.5, 2.4 - MH / 2), (4.5, SH / 2),
          color=LINK_G, ls="--", lw=1.2)
    t(ax, 4.68, 1.50, "read", fs=8, style="italic", ha="left")

    # ── Memory writes from S3 (red dashed) ──────────────────
    # Short write: S3.north → up to y=2.4 → left to B.east
    polyline(ax, [(9.0, SH / 2), (9.0, 2.4),
                  (4.5 + SW / 2, 2.4)],
             color=LINK_W, ls="--", lw=1.2)
    t(ax, 7.55, 2.55, "write", fs=8, style="italic", color=LINK_W)
    t(ax, 9.40, 1.40, r"$r_o^{k+1}$", fs=8.5, style="italic", color=LINK_W)

    # Long write: S3.north → up → across left → mo.north
    polyline(ax, [(9.0, SH / 2), (9.0, 3.35),
                  (0, 3.35), (0, 2.4 + MH / 2)],
             color=LINK_W, ls="--", lw=1.2)
    t(ax, 7.78, 3.50, "write", fs=8, style="italic", color=LINK_W)

    # ── Workboard read/write ───────────────────────────────
    arrow(ax, (4.5 - 0.55, -2.1 + MH / 2), (4.5 - 0.55, -SH / 2),
          color=LINK_G, ls="--", lw=1.2)
    t(ax, 4.5 - 0.75, -1.45, "read", fs=8, style="italic", ha="right")
    arrow(ax, (4.5 + 0.55, -SH / 2), (4.5 + 0.55, -2.1 + MH / 2),
          color=LINK_G, ls="--", lw=1.2)
    t(ax, 4.5 + 0.75, -1.45, "write", fs=8, style="italic", ha="left")

    # ── Output convergence (top): branches from mo & B → out ─
    # mo.north (slightly right offset) up to 3.85 then right
    ax.plot([0.30, 0.30, 6.0], [2.4 + MH / 2, 3.85, 3.85],
            color="black", lw=1.4, zorder=4)
    # B.north up to 3.85 then right
    ax.plot([4.5, 4.5, 6.0], [2.4 + MH / 2, 3.85, 3.85],
            color="black", lw=1.4, zorder=4)
    # Junction → right → down to outTrain
    polyline(ax, [(6.0, 3.85), (out_x, 3.85), (out_x, 0.55)],
             lw=1.4)

    fig.tight_layout(pad=0.4)
    fig.savefig("figures/train_flow.png", dpi=220, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("figures/train_flow.png")


# ══════════════════════════════════════════════════════════════
# 2. Inference flow
# ══════════════════════════════════════════════════════════════
def make_inference():
    fig, ax = plt.subplots(figsize=(13.5, 7.0))
    ax.set_xlim(-3.5, 11.8)
    ax.set_ylim(-4.3, 3.6)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Stages (only Orchestrate + Execute) ───────────────
    SW, SH = 3.6, 1.7
    box(ax, 0,   0, SW, SH, S1_FILL, S1_EDGE)
    box(ax, 4.6, 0, SW, SH, S2_FILL, S2_EDGE)

    # Stage 1
    t(ax, 0,  0.45, "Stage 1: Orchestrate", fs=10.5, w="bold")
    t(ax, 0,  0.10, "Decompose task", fs=9)
    t(ax, 0, -0.45,
      r"$\mathbf{\tau}\sim\pi_o(\cdot\mid q,\mathcal{S}_o^{*})$", fs=8.8)

    # Stage 2
    t(ax, 4.6,  0.45, "Stage 2: Execute", fs=10.5, w="bold")
    t(ax, 4.6,  0.10, "Parallel worker loop", fs=9)
    t(ax, 4.6, -0.45,
      r"$x_i^{t+1}\sim\pi_w^{(i)}(\cdot\mid\tau_i, m_e^t, s_i)$", fs=8.8)

    # ── Output (plain text, no box) ───────────────────────
    out_x = 9.3
    t(ax, out_x,  0.20, "Big Table", fs=10.5, w="bold")
    t(ax, out_x, -0.25, r"$X$", fs=12)

    # ── Top memories (frozen) ────────────────────────────
    MH = 1.5
    box(ax, 0,   2.35, SW, MH, MB_FILL, MB_EDGE)
    t(ax, 0,    2.75, r"Orch. Skill Bank $\mathcal{S}_o^{*}$",
      fs=9.5, w="bold")
    t(ax, 0,    2.30, "decomposition strategies", fs=8)
    t(ax, 0,    1.95, "semantic retrieval", fs=8)

    box(ax, 4.6, 2.35, SW, MH, MB_FILL, MB_EDGE)
    t(ax, 4.6,  2.75, r"Worker Skill Bank $\mathcal{S}_w^{*}$",
      fs=9.5, w="bold")
    t(ax, 4.6,  2.30, "execution skills for search", fs=8)
    t(ax, 4.6,  1.95, "semantic retrieval", fs=8)

    # ── Bottom memory (per-query workboard) ──────────────
    box(ax, 4.6, -2.30, SW, 1.5, ME_FILL, ME_EDGE)
    t(ax, 4.6, -1.85, r"Workboard $m_e$", fs=9.5, w="bold")
    t(ax, 4.6, -2.25, "Low-level Coordination", fs=8.5)
    t(ax, 4.6, -2.65,
      r"$m_e^{t+1}=\mathcal{M}_e(m_e^t,\{h_i^{t+1}\}_i)$", fs=8)

    # ── Input (plain text, left) ─────────────────────────
    in_x = -2.4
    t(ax, in_x,  0.20, "User Query", fs=10.5, w="bold")
    t(ax, in_x, -0.25, r"$q$", fs=12)

    # ── Phase separators ─────────────────────────────────
    sepL = -1.45
    sepR = (4.6 + SW / 2 + out_x) / 2
    ax.plot([sepL, sepL], [-3.6, 3.2], ls="--", color=SEP_C, lw=0.8, zorder=1)
    ax.plot([sepR, sepR], [-3.6, 3.2], ls="--", color=SEP_C, lw=0.8, zorder=1)

    t(ax, in_x,  -3.85, "Input",           fs=10.5, w="bold")
    t(ax, 2.3,   -3.85, "Inference Phase", fs=10.5, w="bold")
    t(ax, out_x, -3.85, "Output",          fs=10.5, w="bold")

    # ── Main horizontal flow ─────────────────────────────
    arrow(ax, (in_x + 0.55, 0), (-SW / 2, 0), lw=1.6)
    arrow(ax, (SW / 2, 0), (4.6 - SW / 2, 0), lw=1.6)
    t(ax, 2.3,  0.22, r"$\mathbf{\tau}$", fs=9, style="italic")
    arrow(ax, (4.6 + SW / 2, 0), (out_x - 0.55, 0), lw=1.6)
    t(ax, 7.85, 0.22, "aggregate", fs=8.5, style="italic")

    # ── Memory reads ─────────────────────────────────────
    arrow(ax, (0,   2.35 - MH / 2), (0,   SH / 2),
          color="#444444", ls="--", lw=1.2)
    t(ax, 0.22, 1.30, "read", fs=8, style="italic", ha="left")
    arrow(ax, (4.6, 2.35 - MH / 2), (4.6, SH / 2),
          color="#444444", ls="--", lw=1.2)
    t(ax, 4.82, 1.30, "read", fs=8, style="italic", ha="left")

    # ── Workboard read / write ──────────────────────────
    arrow(ax, (4.6 - 0.65, -2.30 + 0.75), (4.6 - 0.65, -SH / 2),
          color="#444444", ls="--", lw=1.2)
    arrow(ax, (4.6 + 0.65, -SH / 2), (4.6 + 0.65, -2.30 + 0.75),
          color="#444444", ls="--", lw=1.2)

    fig.tight_layout(pad=0.4)
    fig.savefig("figures/inference_flow.png", dpi=220, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("figures/inference_flow.png")


if __name__ == "__main__":
    make_training()
    make_inference()
