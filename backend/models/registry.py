"""
Model Registry — Versioned ML model storage and lifecycle management.

Structure:
  model_registry/
  ├── target_{name}/
  │   ├── v1/
  │   │   ├── model.pkl         (serialized sklearn/xgboost model)
  │   │   ├── metadata.json     (metrics, features, training date)
  │   │   └── dataset_hash.txt  (hash of training data used)
  │   ├── v2/
  │   └── active.txt            (contains version number of active model)

Rollback:
  - Admin can roll back to any of the last MAX_ROLLBACK_VERSIONS versions
  - Rollback deletes all datasets and models created after the target version
"""
from __future__ import annotations

import json
import os
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import settings


class ModelRegistry:
    def __init__(self):
        self.base_path = Path(settings.model_registry_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.max_versions = settings.max_rollback_versions

    def _target_dir(self, target: str) -> Path:
        return self.base_path / f"target_{target}"

    def _version_dir(self, target: str, version: int) -> Path:
        return self._target_dir(target) / f"v{version}"

    def _active_file(self, target: str) -> Path:
        return self._target_dir(target) / "active.txt"

    # ── Version operations ─────────────────────────────────────────────────

    def list_targets(self) -> list[str]:
        return [
            d.name.replace("target_", "")
            for d in self.base_path.iterdir()
            if d.is_dir() and d.name.startswith("target_")
        ]

    def list_versions(self, target: str) -> list[int]:
        target_dir = self._target_dir(target)
        if not target_dir.exists():
            return []
        versions = []
        for d in target_dir.iterdir():
            if d.is_dir() and d.name.startswith("v"):
                try:
                    versions.append(int(d.name[1:]))
                except ValueError:
                    pass
        return sorted(versions)

    def get_active_version(self, target: str) -> Optional[int]:
        active_file = self._active_file(target)
        if not active_file.exists():
            return None
        return int(active_file.read_text().strip())

    def get_next_version(self, target: str) -> int:
        versions = self.list_versions(target)
        return (max(versions) + 1) if versions else 1

    # ── Model save/load ────────────────────────────────────────────────────

    def save_model(
        self,
        target: str,
        model: Any,
        metadata: dict,
        dataset_hash: str,
        version: Optional[int] = None,
    ) -> int:
        v = version or self.get_next_version(target)
        version_dir = self._version_dir(target, v)
        version_dir.mkdir(parents=True, exist_ok=True)

        # Save model
        with open(version_dir / "model.pkl", "wb") as f:
            pickle.dump(model, f)

        # Save metadata
        metadata["version"] = v
        metadata["saved_at"] = datetime.now(timezone.utc).isoformat()
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2, default=str)

        # Save dataset hash
        (version_dir / "dataset_hash.txt").write_text(dataset_hash)

        return v

    def load_model(self, target: str, version: Optional[int] = None) -> tuple[Any, dict]:
        """Load the model and its metadata. Defaults to active version."""
        v = version or self.get_active_version(target)
        if v is None:
            raise ValueError(f"No active model for target '{target}'")

        version_dir = self._version_dir(target, v)
        if not version_dir.exists():
            raise ValueError(f"Model v{v} for target '{target}' not found.")

        with open(version_dir / "model.pkl", "rb") as f:
            model = pickle.load(f)

        with open(version_dir / "metadata.json") as f:
            metadata = json.load(f)

        return model, metadata

    def get_metadata(self, target: str, version: Optional[int] = None) -> dict:
        v = version or self.get_active_version(target)
        if v is None:
            return {}
        meta_file = self._version_dir(target, v) / "metadata.json"
        if not meta_file.exists():
            return {}
        with open(meta_file) as f:
            return json.load(f)

    # ── Promotion & Rollback ───────────────────────────────────────────────

    def promote(self, target: str, version: int) -> None:
        """Set a version as the active model."""
        version_dir = self._version_dir(target, version)
        if not version_dir.exists():
            raise ValueError(f"Version v{version} for target '{target}' does not exist.")
        self._active_file(target).write_text(str(version))

    def rollback(self, target: str, to_version: int, admin_only: bool = True) -> dict:
        """
        Roll back to a specific version.
        Deletes all model versions and datasets AFTER to_version.
        Returns a summary of what was deleted.
        """
        current_active = self.get_active_version(target)
        versions = self.list_versions(target)

        if to_version not in versions:
            raise ValueError(f"Version v{to_version} does not exist for target '{target}'.")

        deleted_versions = [v for v in versions if v > to_version]
        deleted_paths = []

        for v in deleted_versions:
            vdir = self._version_dir(target, v)
            if vdir.exists():
                shutil.rmtree(vdir)
                deleted_paths.append(str(vdir))

        # Set active to rollback target
        self.promote(target, to_version)

        return {
            "target": target,
            "rolled_back_to": to_version,
            "previous_active": current_active,
            "deleted_versions": deleted_versions,
            "deleted_paths": deleted_paths,
        }

    def can_rollback(self, target: str) -> list[int]:
        """Returns the list of versions available for rollback."""
        versions = self.list_versions(target)
        active = self.get_active_version(target)
        return [v for v in versions if v != active][-self.max_versions:]

    # ── Registry summary ───────────────────────────────────────────────────

    def get_registry_summary(self) -> dict:
        summary = {}
        for target in self.list_targets():
            active = self.get_active_version(target)
            meta = self.get_metadata(target, active)
            summary[target] = {
                "active_version": active,
                "all_versions": self.list_versions(target),
                "metrics": meta.get("metrics", {}),
                "model_type": meta.get("model_type", "unknown"),
                "trained_at": meta.get("saved_at", "unknown"),
                "features": meta.get("features", []),
            }
        return summary


# ── Global singleton ──────────────────────────────────────────────────────────
model_registry = ModelRegistry()
