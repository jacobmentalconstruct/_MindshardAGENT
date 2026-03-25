"""UI-layer state tracking.

Holds transient UI state that doesn't belong in the core config
or persistent registry — selection state, panel visibility, etc.
"""

from dataclasses import dataclass, field


@dataclass
class UIState:
    """Mutable UI-layer state."""

    # Chat
    is_streaming: bool = False
    is_busy: bool = False
    busy_kind: str = ""
    stop_requested: bool = False
    last_user_input: str = ""

    # Model picker
    available_models: list[str] = field(default_factory=list)
    selected_model: str = ""
    model_status: str = "unknown"  # ok, error, loading, unknown

    # Session
    session_title: str = "New Session"
    session_dirty: bool = False

    # Resource status
    cpu_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    gpu_available: bool = False
    vram_used_gb: float = 0.0
    vram_total_gb: float = 0.0

    # Sandbox
    sandbox_root: str = ""
    toolbox_root: str = ""
