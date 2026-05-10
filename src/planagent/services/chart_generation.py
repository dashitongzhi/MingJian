"""SVG chart generation service for debate reports using matplotlib."""

from __future__ import annotations

import io
import math
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.patches as mpatches
import numpy as np

from planagent.config.report_theme import ReportTheme


def _empty_svg(width: int = 800, height: int = 400) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="100%" height="100%" fill="#1a1a2e"/></svg>'
    )


def _fig_to_svg(fig: plt.Figure) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _rc_context():
    """Return a matplotlib rcParams context for safe concurrent use."""
    return matplotlib.rc_context({
        "svg.fonttype": "none",
        "font.sans-serif": [
            "SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC",
            "Microsoft YaHei", "DejaVu Sans", "sans-serif",
        ],
        "axes.unicode_minus": False,
    })


class ChartGenerationService:
    COLORS = ReportTheme.CHART_PALETTE
    BG_COLOR = "#1a1a2e"
    TEXT_COLOR = "#e0e0e0"
    GRID_COLOR = "#333355"

    @classmethod
    def _apply_dark_theme(cls, fig: plt.Figure, axes: list[plt.Axes]) -> None:
        fig.patch.set_facecolor(cls.BG_COLOR)
        for ax in axes:
            ax.set_facecolor(cls.BG_COLOR)
            ax.tick_params(colors=cls.TEXT_COLOR, labelsize=9)
            ax.xaxis.label.set_color(cls.TEXT_COLOR)
            ax.yaxis.label.set_color(cls.TEXT_COLOR)
            ax.title.set_color(cls.TEXT_COLOR)
            for spine in ax.spines.values():
                spine.set_color(cls.GRID_COLOR)
            ax.grid(True, color=cls.GRID_COLOR, alpha=0.4, linewidth=0.5)

    # ------------------------------------------------------------------
    # Confidence trajectory (line chart)
    # ------------------------------------------------------------------
    @staticmethod
    def generate_confidence_trajectory(confidence_data: list[dict]) -> str:
        """Input: [{round: 1, roles: {advocate: 0.8, challenger: 0.6}}]. SVG line chart."""
        try:
            with _rc_context():
                if not confidence_data:
                    return _empty_svg()

                rounds = [d.get("round", i + 1) for i, d in enumerate(confidence_data)]
                roles: dict[str, list[float]] = {}
                for d in confidence_data:
                    for role, val in d.get("roles", {}).items():
                        roles.setdefault(role, []).append(val)

                fig, ax = plt.subplots(figsize=(8, 4))
                fig.patch.set_facecolor(ChartGenerationService.BG_COLOR)
                ax.set_facecolor(ChartGenerationService.BG_COLOR)

                for idx, (role, values) in enumerate(roles.items()):
                    color = ChartGenerationService.COLORS[idx % len(ChartGenerationService.COLORS)]
                    ax.plot(rounds[: len(values)], values, marker="o", linewidth=2,
                            markersize=6, color=color, label=role)

                ax.set_xlabel("轮次", fontsize=11, color=ChartGenerationService.TEXT_COLOR)
                ax.set_ylabel("置信度", fontsize=11, color=ChartGenerationService.TEXT_COLOR)
                ax.set_title("辩论置信度变化轨迹", fontsize=13, fontweight="bold",
                             color=ChartGenerationService.TEXT_COLOR)
                ax.set_ylim(0, 1.05)
                ax.legend(facecolor=ChartGenerationService.BG_COLOR, edgecolor=ChartGenerationService.GRID_COLOR,
                          labelcolor=ChartGenerationService.TEXT_COLOR, fontsize=9)
                ChartGenerationService._apply_dark_theme(fig, [ax])
                return _fig_to_svg(fig)
        except Exception:
            return _empty_svg()

    # ------------------------------------------------------------------
    # Argument comparison (horizontal bar chart)
    # ------------------------------------------------------------------
    @staticmethod
    def generate_argument_comparison(support_args: list, challenge_args: list) -> str:
        """Horizontal bar chart comparing support vs challenge arguments."""
        try:
            with _rc_context():
                support = support_args or []
                challenge = challenge_args or []
                if not support and not challenge:
                    return _empty_svg()

                support_labels = [a.get("label", a.get("text", f"S{i+1}")) for i, a in enumerate(support)]
                support_scores = [a.get("score", a.get("strength", 0.5)) for a in support]
                challenge_labels = [a.get("label", a.get("text", f"C{i+1}")) for i, a in enumerate(challenge)]
                challenge_scores = [a.get("score", a.get("strength", 0.5)) for a in challenge]

                all_labels = support_labels + challenge_labels
                all_scores = support_scores + challenge_scores
                colors = ([ChartGenerationService.COLORS[0]] * len(support) +
                          [ChartGenerationService.COLORS[1]] * len(challenge))

                fig, ax = plt.subplots(figsize=(8, max(4, len(all_labels) * 0.5 + 1)))
                y_pos = np.arange(len(all_labels))
                ax.barh(y_pos, all_scores, color=colors, edgecolor="none", height=0.6)
                ax.set_yticks(y_pos)
                ax.set_yticklabels(all_labels, fontsize=9, color=ChartGenerationService.TEXT_COLOR)
                ax.set_xlabel("论证强度", fontsize=11, color=ChartGenerationService.TEXT_COLOR)
                ax.set_title("论点对比：支持 vs 质疑", fontsize=13, fontweight="bold",
                             color=ChartGenerationService.TEXT_COLOR)
                ax.invert_yaxis()

                # Legend proxy
                legend_elements = [
                    mpatches.Patch(facecolor=ChartGenerationService.COLORS[0], label="支持方"),
                    mpatches.Patch(facecolor=ChartGenerationService.COLORS[1], label="质疑方"),
                ]
                ax.legend(handles=legend_elements, facecolor=ChartGenerationService.BG_COLOR,
                          edgecolor=ChartGenerationService.GRID_COLOR,
                          labelcolor=ChartGenerationService.TEXT_COLOR, fontsize=9, loc="lower right")

                ChartGenerationService._apply_dark_theme(fig, [ax])
                return _fig_to_svg(fig)
        except Exception:
            return _empty_svg()

    # ------------------------------------------------------------------
    # Evidence heatmap
    # ------------------------------------------------------------------
    @staticmethod
    def generate_evidence_heatmap(evidence_matrix: list[dict]) -> str:
        """Heatmap: argument x source, color = strength."""
        try:
            with _rc_context():
                if not evidence_matrix:
                    return _empty_svg()

                arguments = [e.get("argument", f"论点{i+1}") for i, e in enumerate(evidence_matrix)]
                # Collect all source names
                all_sources: list[str] = []
                for e in evidence_matrix:
                    for s in e.get("sources", {}):
                        if s not in all_sources:
                            all_sources.append(s)
                if not all_sources:
                    return _empty_svg()

                matrix = np.zeros((len(arguments), len(all_sources)))
                for i, e in enumerate(evidence_matrix):
                    for j, src in enumerate(all_sources):
                        matrix[i, j] = e.get("sources", {}).get(src, 0.0)

                fig, ax = plt.subplots(figsize=(8, max(4, len(arguments) * 0.6 + 1)))
                cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
                    "debate", ["#1a1a2e", "#4ecdc4", "#ffd93d"], N=256)
                im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)

                ax.set_xticks(np.arange(len(all_sources)))
                ax.set_xticklabels(all_sources, fontsize=9, rotation=30, ha="right",
                                   color=ChartGenerationService.TEXT_COLOR)
                ax.set_yticks(np.arange(len(arguments)))
                ax.set_yticklabels(arguments, fontsize=9, color=ChartGenerationService.TEXT_COLOR)
                ax.set_title("证据强度热力图", fontsize=13, fontweight="bold",
                             color=ChartGenerationService.TEXT_COLOR)

                cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
                cbar.ax.tick_params(colors=ChartGenerationService.TEXT_COLOR, labelsize=8)
                cbar.set_label("强度", color=ChartGenerationService.TEXT_COLOR, fontsize=9)

                ChartGenerationService._apply_dark_theme(fig, [ax])
                return _fig_to_svg(fig)
        except Exception:
            return _empty_svg()

    # ------------------------------------------------------------------
    # Role radar (spider chart)
    # ------------------------------------------------------------------
    @staticmethod
    def generate_role_radar(role_scores: dict) -> str:
        """Radar/spider chart for multi-dimensional role evaluation.
        
        Input: {dimension_name: score, ...} where score in [0, 1].
        """
        try:
            with _rc_context():
                if not role_scores:
                    return _empty_svg()

                labels = list(role_scores.keys())
                values = list(role_scores.values())
                N = len(labels)
                if N < 3:
                    return _empty_svg(600, 600)

                angles = [n / float(N) * 2 * math.pi for n in range(N)]
                values_closed = values + [values[0]]
                angles_closed = angles + [angles[0]]

                fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
                ax.set_facecolor(ChartGenerationService.BG_COLOR)
                fig.patch.set_facecolor(ChartGenerationService.BG_COLOR)

                ax.plot(angles_closed, values_closed, color=ChartGenerationService.COLORS[0],
                        linewidth=2, linestyle="-")
                ax.fill(angles_closed, values_closed, color=ChartGenerationService.COLORS[0], alpha=0.25)

                ax.set_xticks(angles)
                ax.set_xticklabels(labels, fontsize=10, color=ChartGenerationService.TEXT_COLOR)
                ax.set_ylim(0, 1)
                ax.set_yticks([0.25, 0.5, 0.75, 1.0])
                ax.set_yticklabels(["0.25", "0.5", "0.75", "1.0"],
                                   fontsize=7, color=ChartGenerationService.TEXT_COLOR)
                ax.set_title("角色多维评估", fontsize=13, fontweight="bold", pad=20,
                             color=ChartGenerationService.TEXT_COLOR)
                ax.spines["polar"].set_color(ChartGenerationService.GRID_COLOR)
                ax.grid(color=ChartGenerationService.GRID_COLOR, alpha=0.4)

                ChartGenerationService._apply_dark_theme(fig, [ax])
                return _fig_to_svg(fig)
        except Exception:
            return _empty_svg(600, 600)

    # ------------------------------------------------------------------
    # Generate all charts
    # ------------------------------------------------------------------
    @staticmethod
    def generate_all_charts(debate_data: dict) -> dict[str, str]:
        """Calls all above, returns {chart_name: svg_string}."""
        charts: dict[str, str] = {}

        charts["confidence_trajectory"] = ChartGenerationService.generate_confidence_trajectory(
            debate_data.get("confidence_data", []))

        charts["argument_comparison"] = ChartGenerationService.generate_argument_comparison(
            debate_data.get("support_args", []),
            debate_data.get("challenge_args", []))

        charts["evidence_heatmap"] = ChartGenerationService.generate_evidence_heatmap(
            debate_data.get("evidence_matrix", []))

        charts["role_radar"] = ChartGenerationService.generate_role_radar(
            debate_data.get("role_scores", {}))

        return charts
