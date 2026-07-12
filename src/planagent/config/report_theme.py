"""Report theme configuration — color palettes and constants for debate report generation."""


class ReportTheme:
    # Dark theme
    DARK_BG = "#0f0f1a"
    DARK_SURFACE = "#1a1a2e"
    DARK_CARD = "#252540"
    DARK_TEXT = "#e0e0e0"
    DARK_TEXT_SECONDARY = "#a0a0b0"
    DARK_BORDER = "#333355"

    # Role colors
    ROLE_COLORS = {
        "advocate": "#4ecdc4",
        "challenger": "#ff6b6b",
        "arbitrator": "#ffd93d",
        "intel_analyst": "#6c5ce7",
        "geo_expert": "#a8e6cf",
        "econ_analyst": "#fdcb6e",
        "military_strategist": "#e17055",
        "tech_foresight": "#00b894",
        "social_impact": "#fd79a8",
    }

    CHART_PALETTE = ["#4ecdc4", "#ff6b6b", "#ffd93d", "#6c5ce7", "#a8e6cf"]

    EVIDENCE_STRENGTH = {
        "strong": "#00b894",
        "moderate": "#fdcb6e",
        "weak": "#e17055",
        "speculative": "#ff6b6b",
    }

    VERDICT_COLORS = {
        "ACCEPTED": "#00b894",
        "REJECTED": "#ff6b6b",
        "CONDITIONAL": "#fdcb6e",
    }

    FONT_SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    FONT_MONO = '"SF Mono", "Fira Code", monospace'


def get_theme(theme_name: str = "dark") -> dict:
    """Return all theme constants as a dict for template rendering."""
    return {
        "bg": ReportTheme.DARK_BG,
        "surface": ReportTheme.DARK_SURFACE,
        "card": ReportTheme.DARK_CARD,
        "text": ReportTheme.DARK_TEXT,
        "text_secondary": ReportTheme.DARK_TEXT_SECONDARY,
        "border": ReportTheme.DARK_BORDER,
        "role_colors": ReportTheme.ROLE_COLORS,
        "chart_palette": ReportTheme.CHART_PALETTE,
        "evidence_strength": ReportTheme.EVIDENCE_STRENGTH,
        "verdict_colors": ReportTheme.VERDICT_COLORS,
        "font_sans": ReportTheme.FONT_SANS,
        "font_mono": ReportTheme.FONT_MONO,
    }
