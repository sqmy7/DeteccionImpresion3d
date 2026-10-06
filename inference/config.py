from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    redis_url: str
    models_dir: Path = Path("/app/models")
    storage_root: Path = Path("/app/storage/snapshots")
    onnx_filename: str = "best_fp32.onnx"
    # Name of the model_versions row this model's detections get attributed to. Bump it
    # whenever the .onnx is replaced by a retrained model: if the name is reused, new
    # detections would silently be attributed to the OLD version's row (the worker only
    # catches the case where the class list itself changed). Named onnx_* rather than
    # model_* because pydantic reserves the model_ prefix for its own fields.
    onnx_version_name: str = "yolo11s-trained-v1-fp32"
    intra_op_num_threads: int = 1
    # Global (all classes). FINAL: calibrated on the 841-image test split with the deployed FP32 model - at 0.25 the
    # image-level precision/recall is 0.997/0.921 overall (per-class numbers in models/best_fp32.metrics.json), above
    # the 90% precision floor the project prioritizes. Per-class thresholds were deliberately NOT implemented. Known
    # weak spot: blob_over_extrusion (image precision 0.56, never reaches 90% at any threshold; needs data, not a
    # threshold - see inference/training/README.md, "Limitaciones conocidas"; shown as an informational class in the UI,
    # frontend/src/config/defectClasses.ts). Re-run notebook section 8c after any
    # retraining before trusting 0.25. Override with the CONFIDENCE_THRESHOLD env var.
    confidence_threshold: float = 0.25
    heartbeat_path: Path = Path("/tmp/heartbeat")


settings = Settings()
