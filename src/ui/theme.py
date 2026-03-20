"""Cyberpunk UI theme constants.

Dark base with neon accent colors. All UI components pull colors
and fonts from here for consistency.
"""

# ── Base palette ──────────────────────────────────────────────
BG_DARK      = "#0a0e17"       # deepest background
BG_MID       = "#111827"       # panels, cards
BG_LIGHT     = "#1a2236"       # input fields, hover states
BG_SURFACE   = "#1e293b"       # raised surfaces

# ── Neon accents ──────────────────────────────────────────────
CYAN         = "#00f0ff"       # primary accent — headers, active elements
MAGENTA      = "#ff2d7b"       # warnings, tool activity
GREEN        = "#39ff14"       # success, status OK
AMBER        = "#ffb300"       # caution, pending
RED          = "#ff3b3b"       # errors
PURPLE       = "#a855f7"       # model/AI responses
BLUE_SOFT    = "#60a5fa"       # links, secondary info

# ── Text ──────────────────────────────────────────────────────
TEXT_PRIMARY  = "#e2e8f0"      # main body text
TEXT_DIM      = "#64748b"      # metadata, timestamps
TEXT_BRIGHT   = "#f8fafc"      # headings, emphasis
TEXT_INPUT    = "#cbd5e1"      # input field text

# ── Borders and dividers ─────────────────────────────────────
BORDER        = "#1e3a5f"      # subtle borders
BORDER_GLOW   = "#00f0ff"      # focused / active borders
SCROLLBAR_BG  = "#0f1729"
SCROLLBAR_FG  = "#2a3f5f"

# ── Specialised backgrounds ──────────────────────────────────
BG_DEEPEST    = "#060a10"      # CLI terminal, deepest inset
BG_LOG        = "#080c14"      # activity log background
BG_AGENT      = "#13182b"      # agent message card
BG_TOOL       = "#17122a"      # tool message card

# ── Tag colours ──────────────────────────────────────────────
TS_DIM        = "#3a4a6b"      # timestamp tags in logs

# ── Fonts ─────────────────────────────────────────────────────
FONT_FAMILY      = "Consolas"
FONT_FAMILY_ALT  = "Cascadia Code"
FONT_SIZE_SM     = 9
FONT_SIZE_MD     = 10
FONT_SIZE_LG     = 12
FONT_SIZE_XL     = 14
FONT_SIZE_TITLE  = 16

FONT_BODY     = (FONT_FAMILY, FONT_SIZE_MD)
FONT_SMALL    = (FONT_FAMILY, FONT_SIZE_SM)
FONT_HEADING  = (FONT_FAMILY, FONT_SIZE_LG, "bold")
FONT_TITLE    = (FONT_FAMILY, FONT_SIZE_TITLE, "bold")
FONT_INPUT    = (FONT_FAMILY, FONT_SIZE_MD)
FONT_LOG      = (FONT_FAMILY, FONT_SIZE_SM)
FONT_BUTTON   = (FONT_FAMILY, FONT_SIZE_MD, "bold")


# ── DPI scaling ──────────────────────────────────────────────
def enable_dpi_awareness(root) -> float:
    """Enable Windows DPI awareness and return the scaling factor.

    Call BEFORE creating any widgets. Returns the DPI scale (1.0 = 96 DPI).
    On non-Windows platforms, this is a no-op returning 1.0.
    """
    import sys
    scale = 1.0
    if sys.platform == "win32":
        try:
            import ctypes
            # Per-Monitor V2 awareness (Windows 10 1703+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                # Fallback: System DPI awareness
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    # Let Tk figure out the scaling from the OS DPI
    try:
        scale = root.tk.call("tk", "scaling")
        # tk scaling returns pixels-per-point; 1.333... = 96 DPI (standard)
        # Normalise so 1.0 = "standard 96 DPI"
        scale = float(scale) / 1.333333
        if scale < 0.75:
            scale = 1.0  # sanity floor
    except Exception:
        scale = 1.0
    return scale
