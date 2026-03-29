"""Core Prompt Lab contracts, storage, validation, and runtime seams.

This package is the app-owned home for Prompt Lab's canonical data objects,
storage conventions, validation rules, and publish/apply seams. It intentionally
contains import-safe Prompt Lab foundations for Phase 1C.
"""

from .contracts import (
    ACTIVE_PROMPT_LAB_STATE_KIND,
    BINDING_RECORD_KIND,
    EVAL_RUN_KIND,
    EXECUTION_PLAN_KIND,
    PUBLISHED_PROMPT_LAB_PACKAGE_KIND,
    PROMOTION_RECORD_KIND,
    PROMPT_BUILD_ARTIFACT_KIND,
    PROMPT_PROFILE_KIND,
    TRAINING_RUN_KIND,
    TRAINING_SUITE_KIND,
    VALIDATION_SNAPSHOT_KIND,
    ActivePromptLabState,
    BindingRecord,
    EvalRun,
    ExecutionNode,
    ExecutionPlan,
    PublishedPromptLabPackage,
    PromptBuildArtifact,
    PromptProfile,
    PromptSourceRef,
    PromotionRecord,
    TrainingRun,
    TrainingSuite,
    ValidationSnapshot,
)
from .paths import PromptLabPaths, resolve_prompt_lab_paths
from .operation_log import PromptLabOperationLog
from .promotion import PromotionStatus, get_promotion_status
from .runtime_loader import (
    PromptLabRuntimeBundle,
    describe_active_prompt_lab_runtime,
    load_active_prompt_lab_runtime,
)
from .services import PromptLabServiceBundle, build_prompt_lab_services
from .storage import PromptLabStorage, build_prompt_lab_storage, ensure_prompt_lab_directories
from .training_service import (
    DEFAULT_GENERATOR_MODEL,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_TARGET_MODEL,
    DEFAULT_TRAINING_SUITE_ID,
    TrainingRunResult,
    TrainingService,
)
from .validation import (
    validate_active_state,
    validate_package_selection,
    validate_prompt_lab_state,
)

__all__ = [
    "ACTIVE_PROMPT_LAB_STATE_KIND",
    "BINDING_RECORD_KIND",
    "BindingRecord",
    "EVAL_RUN_KIND",
    "EvalRun",
    "EXECUTION_PLAN_KIND",
    "ExecutionNode",
    "ExecutionPlan",
    "PUBLISHED_PROMPT_LAB_PACKAGE_KIND",
    "PROMOTION_RECORD_KIND",
    "PROMPT_BUILD_ARTIFACT_KIND",
    "PROMPT_PROFILE_KIND",
    "TRAINING_RUN_KIND",
    "TRAINING_SUITE_KIND",
    "ActivePromptLabState",
    "PromptBuildArtifact",
    "PromptLabPaths",
    "PromptLabOperationLog",
    "PromptLabRuntimeBundle",
    "PromptLabStorage",
    "PromptLabServiceBundle",
    "PromptProfile",
    "PromptSourceRef",
    "PublishedPromptLabPackage",
    "PromotionStatus",
    "PromotionRecord",
    "TrainingRun",
    "TrainingRunResult",
    "TrainingService",
    "TrainingSuite",
    "VALIDATION_SNAPSHOT_KIND",
    "ValidationSnapshot",
    "DEFAULT_GENERATOR_MODEL",
    "DEFAULT_JUDGE_MODEL",
    "DEFAULT_TARGET_MODEL",
    "DEFAULT_TRAINING_SUITE_ID",
    "build_prompt_lab_services",
    "build_prompt_lab_storage",
    "ensure_prompt_lab_directories",
    "describe_active_prompt_lab_runtime",
    "get_promotion_status",
    "load_active_prompt_lab_runtime",
    "resolve_prompt_lab_paths",
    "validate_active_state",
    "validate_package_selection",
    "validate_prompt_lab_state",
]
