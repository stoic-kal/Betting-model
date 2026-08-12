import glob
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FETCH_NOT_ATTEMPTED = "not_attempted"
FETCH_OK = "attempted_succeeded"
FETCH_FAILED = "attempted_failed"
FETCH_NOT_INSTRUMENTED = "not_instrumented"

VALIDATION_PASSED = "passed"
VALIDATION_FAILED = "failed_bounds_check"
VALIDATION_NOT_RUN = "not_run"

FALLBACK_NONE = "none"
FALLBACK_APPLIED = "applied"
FALLBACK_NOT_INSTRUMENTED = "not_instrumented"

SERIALIZATION_WRITTEN = "written"
SERIALIZATION_OMITTED = "omitted_by_writer"
SERIALIZATION_NOT_INSTRUMENTED = "not_instrumented"

SNAPSHOT_PRESENT = "present"
SNAPSHOT_NULL = "key_present_value_null"
SNAPSHOT_KEY_ABSENT = "key_absent_from_payload"
SNAPSHOT_ABSENT = "no_snapshot_payload_persisted"

APPLICABILITY_APPLICABLE = "applicable"
APPLICABILITY_NOT_APPLICABLE = "not_applicable_field_did_not_exist_at_this_version"
APPLICABILITY_UNDETERMINED = "undetermined"

REGISTRY_GLOB = "models/registry/*/*/metadata.json"
CONTEXT_SKIP_LOG = "data/context_features_skip_log.jsonl"
TOTALS_TARGET_SKIP_LOG = "data/totals_target_skip_log.jsonl"
PICKS_DB = "database/picks.db"
PROVENANCE_REPORT_PATH = "reports/training/field_provenance_report.json"


def _abs(relative_path):
    p = Path(relative_path)
    return p if p.is_absolute() else REPO_ROOT / p


def insufficient_evidence(field_name, searched):
    return (
        f"insufficient information to determine root cause for '{field_name}': "
        f"searched {', '.join(searched)} and none of them carried an entry for this field"
    )


def _derive_confidence(fetch_status, validation_status, fallback_status, snapshot_status):
    if snapshot_status in (SNAPSHOT_ABSENT, SNAPSHOT_KEY_ABSENT):
        return 0.0
    if snapshot_status == SNAPSHOT_NULL:
        return 0.0
    if fallback_status == FALLBACK_APPLIED:
        return 0.25 if fetch_status == FETCH_FAILED else 0.4
    if validation_status == VALIDATION_FAILED:
        return 0.25
    if fetch_status == FETCH_OK and validation_status == VALIDATION_PASSED:
        return 1.0
    if fetch_status == FETCH_OK:
        return 0.8
    if fetch_status == FETCH_NOT_INSTRUMENTED:
        return 0.5
    return 0.5


@dataclass
class FieldProvenance:
    field_name: str
    source: str
    fetch_status: str
    validation_status: str
    fallback_status: str
    serialization_status: str
    snapshot_status: str
    schema_version: str
    timestamp: str
    confidence: float
    reason_if_missing: str
    applicability: str = APPLICABILITY_APPLICABLE
    evidence: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class ProvenanceRecorder:
    def __init__(self, schema_version, timestamp=None):
        self.schema_version = str(schema_version)
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self._stages = {}

    def _entry(self, field_name):
        return self._stages.setdefault(
            field_name,
            {
                "source": None,
                "fetch_status": FETCH_NOT_ATTEMPTED,
                "validation_status": VALIDATION_NOT_RUN,
                "fallback_status": FALLBACK_NONE,
                "reason": None,
                "evidence": [],
            },
        )

    def _apply(self, fields, **updates):
        evidence = updates.pop("evidence", None)
        for name in fields:
            entry = self._entry(name)
            entry.update({k: v for k, v in updates.items() if v is not None})
            if evidence:
                entry["evidence"].append(evidence)

    def fetch_attempted(self, fields, source, evidence=None):
        self._apply(fields, source=source, fetch_status=FETCH_OK, evidence=evidence)

    def fetch_failed(self, fields, source, error, evidence=None):
        self._apply(
            fields,
            source=source,
            fetch_status=FETCH_FAILED,
            reason=f"fetch from {source} raised {type(error).__name__}: {error}"
            if isinstance(error, BaseException)
            else f"fetch from {source} did not return usable data: {error}",
            evidence=evidence,
        )

    def fetch_skipped(self, fields, source, reason, evidence=None):
        self._apply(
            fields,
            source=source,
            fetch_status=FETCH_NOT_ATTEMPTED,
            reason=reason,
            evidence=evidence,
        )

    def fallback_applied(self, fields, source, reason, evidence=None):
        self._apply(
            fields,
            source=source,
            fallback_status=FALLBACK_APPLIED,
            reason=reason,
            evidence=evidence,
        )

    def validation_result(self, checked_fields, invalid_fields):
        invalid = set(invalid_fields)
        for name in checked_fields:
            entry = self._entry(name)
            entry["validation_status"] = VALIDATION_FAILED if name in invalid else VALIDATION_PASSED
            if name in invalid:
                entry["fallback_status"] = FALLBACK_APPLIED
                entry["reason"] = (
                    "value failed the FEATURE_BOUNDS range check in "
                    "pipeline/features_common.py:validate_features and was replaced by its FEATURE_FALLBACKS value"
                )

    def degraded_fields(self):
        return sorted(
            name
            for name, entry in self._stages.items()
            if entry["fallback_status"] == FALLBACK_APPLIED
            or entry["fetch_status"] == FETCH_FAILED
            or entry["validation_status"] == VALIDATION_FAILED
        )

    def finalize(self, values):
        records = {}
        for name in sorted(set(self._stages) | set(values or {})):
            entry = self._entry(name)
            if values is None or name not in values:
                snapshot_status = SNAPSHOT_KEY_ABSENT
                serialization_status = SERIALIZATION_OMITTED
            elif values[name] is None:
                snapshot_status = SNAPSHOT_NULL
                serialization_status = SERIALIZATION_WRITTEN
            else:
                snapshot_status = SNAPSHOT_PRESENT
                serialization_status = SERIALIZATION_WRITTEN
            reason = entry["reason"]
            if reason is None and snapshot_status in (SNAPSHOT_NULL, SNAPSHOT_KEY_ABSENT):
                reason = insufficient_evidence(
                    name,
                    [
                        "the in-process provenance recorder for this build",
                        "the serialized value map handed to the writer",
                    ],
                )
            records[name] = FieldProvenance(
                field_name=name,
                source=entry["source"] or "not recorded by any producer in this build",
                fetch_status=entry["fetch_status"],
                validation_status=entry["validation_status"],
                fallback_status=entry["fallback_status"],
                serialization_status=serialization_status,
                snapshot_status=snapshot_status,
                schema_version=self.schema_version,
                timestamp=self.timestamp,
                confidence=_derive_confidence(
                    entry["fetch_status"],
                    entry["validation_status"],
                    entry["fallback_status"],
                    snapshot_status,
                ),
                reason_if_missing=reason or "",
                evidence=list(entry["evidence"]),
            ).to_dict()
        return records


_skip_index_cache = {}


def context_skip_index(path=CONTEXT_SKIP_LOG):
    cached = _skip_index_cache.get(path)
    full = _abs(path)
    stamp = full.stat().st_mtime if full.exists() else None
    if cached is not None and cached[0] == stamp:
        return cached[1]
    by_game = {}
    by_feature = {}
    if full.exists():
        with open(full) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                key = (str(entry.get("game")), entry.get("feature"))
                by_game[key] = entry.get("reason")
                stats = by_feature.setdefault(entry.get("feature"), {"count": 0, "reasons": {}})
                stats["count"] += 1
                stats["reasons"][entry.get("reason")] = stats["reasons"].get(entry.get("reason"), 0) + 1
    index = {"by_game_feature": by_game, "by_feature": by_feature, "path": str(path)}
    _skip_index_cache[path] = (stamp, index)
    return index


def registry_schema_history(pattern=REGISTRY_GLOB):
    versions = {}
    for path in glob.glob(str(_abs(pattern))):
        try:
            with open(path) as handle:
                metadata = json.load(handle)
        except (OSError, ValueError):
            continue
        version = metadata.get("feature_schema_version")
        if not version:
            continue
        entry = versions.setdefault(version, {"fields": set(), "first_seen": None, "artifacts": []})
        entry["fields"].update(metadata.get("feature_list") or [])
        trained_at = metadata.get("trained_at")
        if trained_at and (entry["first_seen"] is None or trained_at < entry["first_seen"]):
            entry["first_seen"] = trained_at
        entry["artifacts"].append(os.path.relpath(path, REPO_ROOT))
    return versions


def _version_order(versions):
    return sorted(versions, key=lambda v: (versions[v]["first_seen"] or "", v))


def field_introduced_at(field_name, versions=None):
    versions = registry_schema_history() if versions is None else versions
    for version in _version_order(versions):
        if field_name in versions[version]["fields"]:
            return version
    return None


def classify_training_field_applicability(field_name, row_schema_version, versions=None):
    versions = registry_schema_history() if versions is None else versions
    searched = [f"{len(versions)} registered model metadata artifacts under {REGISTRY_GLOB}"]
    if row_schema_version not in versions:
        return (
            APPLICABILITY_UNDETERMINED,
            insufficient_evidence(field_name, searched + [f"no registered model carries schema version {row_schema_version!r}"]),
            searched,
        )
    if field_name in versions[row_schema_version]["fields"]:
        return (
            APPLICABILITY_APPLICABLE,
            "",
            searched + [f"present in the feature_list of schema version {row_schema_version}"],
        )
    introduced = field_introduced_at(field_name, versions)
    if introduced is None:
        return (
            APPLICABILITY_UNDETERMINED,
            insufficient_evidence(field_name, searched),
            searched,
        )
    return (
        APPLICABILITY_NOT_APPLICABLE,
        f"not applicable — first appears in the feature_list of schema version {introduced} "
        f"(first registered {versions[introduced]['first_seen']}), this row is schema version {row_schema_version}",
        searched + [f"introduced at {introduced} per {versions[introduced]['artifacts'][0]}"],
    )


def snapshot_cohorts(records):
    cohorts = {}
    for record in records:
        snap = record.get("snap") or {}
        signature = frozenset(flatten_snapshot_keys(snap)) if record.get("has_snapshot") else frozenset()
        entry = cohorts.setdefault(
            signature,
            {"rows": 0, "schema_versions": set(), "model_builds": set(), "fields": set(signature)},
        )
        entry["rows"] += 1
        entry["schema_versions"].add(record.get("schema_version"))
        entry["model_builds"].add(record.get("model_build"))
    return cohorts


def _cohort_label(signature, cohorts):
    entry = cohorts.get(signature)
    if not entry:
        return "an unrecognised writer cohort"
    builds = sorted(str(b) for b in entry["model_builds"] if b)
    versions = sorted(str(v) for v in entry["schema_versions"])
    return (
        f"the writer cohort emitting {len(signature)} snapshot keys "
        f"(schema_version {'/'.join(versions) or 'untagged'}, model_build {'/'.join(builds) or 'unrecorded'}, "
        f"{entry['rows']} rows)"
    )


def _cohorts_carrying(field_key, cohorts):
    return [sig for sig in cohorts if field_key in sig]


def reconstruct_snapshot_provenance(record, field_key, snapshot_key, value, cohorts, meta=None,
                                    skip_index=None, status_value=None, status_path=None):
    meta = meta or {}
    snap = record.get("snap") or {}
    flattened = flatten_snapshot_keys(snap)
    signature = frozenset(flattened) if record.get("has_snapshot") else frozenset()
    schema_version = record.get("schema_version")
    searched = []
    evidence = []
    applicability = APPLICABILITY_APPLICABLE
    reason = ""

    if not record.get("has_snapshot"):
        snapshot_status = SNAPSHOT_ABSENT
        serialization_status = SERIALIZATION_OMITTED
        reason = (
            f"no feature_snapshot payload was persisted for this pick at all "
            f"(picks.feature_snapshot is empty; model_build {record.get('model_build')!r}), so no field-level "
            f"provenance was ever written for it"
        )
        evidence.append("picks.feature_snapshot is NULL or empty for this row")
    elif snapshot_key not in flattened:
        snapshot_status = SNAPSHOT_KEY_ABSENT
        serialization_status = SERIALIZATION_OMITTED
        carriers = _cohorts_carrying(snapshot_key, cohorts)
        searched.append("the exact key set every stored feature_snapshot cohort emitted")
        if carriers:
            applicability = APPLICABILITY_NOT_APPLICABLE
            reason = (
                f"not applicable — the key {snapshot_key!r} is absent from every row written by "
                f"{_cohort_label(signature, cohorts)}, and is only ever emitted by "
                f"{'; '.join(_cohort_label(c, cohorts) for c in carriers)}; the writer at this row's code "
                f"version did not produce this field, so the row is not missing it"
            )
            evidence.append(
                f"key absent from all {cohorts[signature]['rows']} rows of this cohort, present in "
                f"{sum(cohorts[c]['rows'] for c in carriers)} rows of later cohorts"
            )
        else:
            reason = insufficient_evidence(field_key, searched + ["no stored snapshot in this database emits this key"])
    elif value is None:
        snapshot_status = SNAPSHOT_NULL
        serialization_status = SERIALIZATION_WRITTEN
        evidence.append(f"key {snapshot_key!r} written by the same cohort with a null value")
    else:
        snapshot_status = SNAPSHOT_PRESENT
        serialization_status = SERIALIZATION_WRITTEN

    fetch_status = FETCH_NOT_INSTRUMENTED
    validation_status = VALIDATION_NOT_RUN
    fallback_status = FALLBACK_NOT_INSTRUMENTED

    if status_value is not None:
        evidence.append(f"snapshot status field {'.'.join(status_path)} = {status_value!r}")
        if status_value in ("TIMEOUT", "API_ERROR"):
            fetch_status = FETCH_FAILED
            fallback_status = FALLBACK_APPLIED
            if not reason:
                reason = (
                    f"the responsible fetch recorded {status_value} in {'.'.join(status_path)} for this row, "
                    f"so the value shown is a fallback, not a live read"
                )
        elif status_value in ("FALLBACK", "fallback_default"):
            fetch_status = FETCH_FAILED
            fallback_status = FALLBACK_APPLIED
            if not reason:
                reason = (
                    f"{'.'.join(status_path)} = {status_value!r} for this row: the live fetch did not return "
                    f"usable data and the documented default was substituted"
                )
        elif status_value == "UNKNOWN":
            fetch_status = FETCH_NOT_ATTEMPTED
            if not reason:
                reason = (
                    f"{'.'.join(status_path)} = 'UNKNOWN', which services/advanced_context_service.py writes when "
                    f"no fetch attempt produced a status at all for this game"
                )
        else:
            fetch_status = FETCH_OK
            fallback_status = FALLBACK_NONE
    elif status_path is not None and snapshot_status != SNAPSHOT_KEY_ABSENT and record.get("has_snapshot"):
        searched.append(f"the snapshot status field {'.'.join(status_path)}")

    if skip_index and snapshot_status in (SNAPSHOT_NULL, SNAPSHOT_KEY_ABSENT):
        logged = skip_index["by_game_feature"].get((str(record.get("game_id")), field_key))
        searched.append(f"{skip_index['path']} keyed by (game, feature)")
        if logged:
            fallback_status = FALLBACK_APPLIED
            reason = f"logged at write time in {skip_index['path']}: {logged}"
            evidence.append("matched a skip-log entry written by pipeline/feature_store.py:_log_context_skip")

    if not reason and snapshot_status in (SNAPSHOT_NULL, SNAPSHOT_ABSENT):
        searched.append("the stored snapshot payload itself")
        reason = insufficient_evidence(field_key, searched)

    return FieldProvenance(
        field_name=field_key,
        source=meta.get("source") or "no source recorded for this field by the writer at this code version",
        fetch_status=fetch_status,
        validation_status=validation_status,
        fallback_status=fallback_status,
        serialization_status=serialization_status,
        snapshot_status=snapshot_status,
        schema_version=str(schema_version) if schema_version is not None else "untagged",
        timestamp=str(snap.get("snapshot_created_at") or record.get("date") or ""),
        confidence=_derive_confidence(fetch_status, validation_status, fallback_status, snapshot_status),
        reason_if_missing=reason,
        applicability=applicability,
        evidence=evidence,
    )


_SOURCE_CACHE = {}


def _python_sources():
    if "files" not in _SOURCE_CACHE:
        files = []
        for path in REPO_ROOT.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT)
            if rel.parts[0] in ("venv", "archive", "__pycache__", "catboost_info", "ios", "node_modules"):
                continue
            files.append(rel)
        _SOURCE_CACHE["files"] = sorted(files)
    return _SOURCE_CACHE["files"]


def locate_field_code(field_name, max_hits=5, writer_markers=("feature_snapshot", "_log_context_skip", "FEATURE_FALLBACKS")):
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(field_name)}(?![A-Za-z0-9_])")
    ranked = []
    for rel in _python_sources():
        try:
            text = (REPO_ROOT / rel).read_text(errors="ignore")
        except OSError:
            continue
        if field_name not in text:
            continue
        lines = [
            f"{rel}:{number}"
            for number, line in enumerate(text.splitlines(), start=1)
            if pattern.search(line)
        ]
        if not lines:
            continue
        is_writer = any(marker in text for marker in writer_markers)
        ranked.append((0 if is_writer else 1, rel.as_posix(), lines))
    ranked.sort()
    hits = []
    for _, _, lines in ranked:
        for entry in lines:
            hits.append(entry)
            if len(hits) >= max_hits:
                return hits
    return hits


def _load_pick_records(db_path=PICKS_DB):
    connection = sqlite3.connect(str(_abs(db_path)))
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT game_id, date, pick_type, status, model_version, model_build, feature_snapshot FROM picks"
    ).fetchall()
    connection.close()
    records = []
    for row in rows:
        record = dict(row)
        try:
            snap = json.loads(record.get("feature_snapshot") or "{}")
        except ValueError:
            snap = {}
        record["snap"] = snap if isinstance(snap, dict) else {}
        record["has_snapshot"] = bool(record.get("feature_snapshot"))
        record["schema_version"] = record["snap"].get("schema_version")
        records.append(record)
    return records


def _skip_log_classification(field_name, skip_index, cohort_games):
    stats = skip_index["by_feature"].get(field_name)
    if not stats:
        return None
    reasons = sorted(stats["reasons"].items(), key=lambda kv: -kv[1])
    coverage = stats["count"] / cohort_games if cohort_games else 0.0
    structural = coverage >= 0.99 and len(reasons) == 1
    return {
        "logged_events": stats["count"],
        "distinct_reasons": len(reasons),
        "dominant_reason": reasons[0][0],
        "coverage_vs_max_logged_feature": round(coverage, 4),
        "verdict": "structural_stub" if structural else "intermittent_data_gap",
    }


def load_feature_catalog_module():
    import importlib.util

    path = REPO_ROOT / "research" / "diagnostics" / "totals" / "feature_catalog.py"
    spec = importlib.util.spec_from_file_location("totals_feature_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot_key_for(field_key):
    for prefix in ("home_starter_usage_", "away_starter_usage_"):
        if field_key.startswith(prefix):
            return f"{prefix.rstrip('_')}.{field_key[len(prefix):]}"
    if field_key.startswith("context_"):
        return f"context.{field_key[len('context_'):]}"
    return field_key


def flatten_snapshot_keys(snap, prefix=""):
    keys = set()
    for key, value in (snap or {}).items():
        path = f"{prefix}{key}"
        keys.add(path)
        if isinstance(value, dict):
            keys |= flatten_snapshot_keys(value, prefix=f"{path}.")
    return keys


def catalog_entries():
    module = load_feature_catalog_module()
    entries = []
    for field_key, meta in module.FEATURE_CATALOG.items():
        entries.append((
            field_key,
            meta,
            snapshot_key_for(field_key),
            meta.get("status_path"),
            lambda record, key=field_key: module.get_feature_value(record, key),
        ))
    return entries


def build_provenance_report(db_path=PICKS_DB):
    records = _load_pick_records(db_path)
    cohorts = snapshot_cohorts([r for r in records if r["pick_type"] == "totals"])
    skip_index = context_skip_index()
    versions = registry_schema_history()

    max_logged = max((s["count"] for s in skip_index["by_feature"].values()), default=0)

    fields = []
    for field_key, meta, snapshot_key, status_path, value_of in catalog_entries():
        applicable_records = [r for r in records if r["pick_type"] == meta.get("applies_to", "totals")]
        rows = []
        for record in applicable_records:
            value = value_of(record)
            status_value = None
            if status_path:
                cursor = record.get("snap") or {}
                for key in status_path:
                    cursor = cursor.get(key) if isinstance(cursor, dict) else None
                status_value = cursor
            rows.append(
                reconstruct_snapshot_provenance(
                    record, field_key, snapshot_key, value, cohorts, meta=meta,
                    skip_index=skip_index, status_value=status_value, status_path=status_path,
                )
            )
        not_applicable = [r for r in rows if r.applicability == APPLICABILITY_NOT_APPLICABLE]
        undetermined = [r for r in rows if r.applicability == APPLICABILITY_UNDETERMINED]
        missing = [
            r for r in rows
            if r.snapshot_status != SNAPSHOT_PRESENT and r.applicability != APPLICABILITY_NOT_APPLICABLE
        ]
        denominator = len(rows) - len(not_applicable)
        skip_stats = _skip_log_classification(field_key, skip_index, max_logged)
        if skip_stats and skip_stats["verdict"] == "structural_stub":
            classification = "bug_unimplemented_stub"
            fix = (
                f"the write path logs the same reason for {skip_stats['logged_events']} of "
                f"{max_logged} logged events, i.e. it never produces a real value: implement the "
                f"computation or drop the field from the feature list"
            )
            user_action = "engineering_fixable"
        elif skip_stats:
            classification = "expected_documented_data_gap"
            fix = f"logged cause is data availability, not wiring: {skip_stats['dominant_reason']}"
            user_action = "engineering_fixable"
        elif not_applicable and not missing:
            classification = "expected_historical_schema_artifact"
            fix = "no fix required — the field did not exist at the writer version these rows were created under"
            user_action = "no_action_required"
        elif missing:
            causes = sorted({r.reason_if_missing for r in missing if r.reason_if_missing})
            statuses = {r.snapshot_status for r in missing}
            if statuses == {SNAPSHOT_ABSENT}:
                classification = "expected_no_snapshot_persisted"
                fix = (
                    f"none available retroactively — all {len(missing)} rows store an empty picks.feature_snapshot, "
                    f"so no per-field value was ever written; current rows are unaffected"
                )
                user_action = "no_action_required"
            elif all(c.startswith("insufficient information") for c in causes):
                classification = "unresolved_insufficient_evidence"
                fix = (
                    "instrument the write path with pipeline/field_provenance.ProvenanceRecorder so future rows "
                    "carry a per-field record; the historical rows cannot be re-derived"
                )
                user_action = "engineering_fixable"
            else:
                classification = "expected_documented_data_gap"
                fix = causes[0]
                user_action = "engineering_fixable"
        else:
            classification = "healthy"
            fix = "none"
            user_action = "no_action_required"

        fields.append({
            "field": field_key,
            "label": meta.get("label", field_key),
            "rows_examined": len(rows),
            "rows_not_applicable": len(not_applicable),
            "rows_undetermined": len(undetermined),
            "rows_missing": len(missing),
            "missing_pct_raw": round(
                (len(missing) + len(not_applicable)) / len(rows) * 100, 1) if rows else None,
            "missing_pct_schema_aware": round(len(missing) / denominator * 100, 1) if denominator else None,
            "root_causes": sorted({r.reason_if_missing for r in rows if r.reason_if_missing}),
            "code_locations": locate_field_code(field_key),
            "classification": classification,
            "requires_user_action": user_action,
            "recommended_fix": fix,
            "skip_log_evidence": skip_stats,
            "sample_provenance": rows[-1].to_dict() if rows else None,
        })

    from pipeline.features_common import CONTEXT_FEATURES

    context_fields = []
    for name, stats in sorted(skip_index["by_feature"].items()):
        verdict = _skip_log_classification(name, skip_index, max_logged)
        context_fields.append({
            "field": name,
            "is_model_feature": name in CONTEXT_FEATURES,
            "logged_events": stats["count"],
            "distinct_logged_reasons": len(stats["reasons"]),
            "dominant_reason": verdict["dominant_reason"],
            "classification": (
                "bug_unimplemented_stub" if verdict["verdict"] == "structural_stub"
                else "expected_documented_data_gap"
            ),
            "requires_user_action": "engineering_fixable",
            "code_locations": locate_field_code(name),
            "recommended_fix": (
                "implement the computation or remove the field from CONTEXT_FEATURES — it never produces a "
                "real value on any game"
                if verdict["verdict"] == "structural_stub"
                else "cause is upstream data availability for specific games, not missing wiring; widen the "
                     "source coverage or accept the documented fallback"
            ),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_sources": {
            "picks_database": db_path,
            "snapshot_writer_cohorts": [
                {
                    "keys": sorted(signature),
                    "rows": entry["rows"],
                    "schema_versions": sorted(str(v) for v in entry["schema_versions"]),
                    "model_builds": sorted(str(b) for b in entry["model_builds"] if b),
                }
                for signature, entry in sorted(cohorts.items(), key=lambda kv: -kv[1]["rows"])
            ],
            "registry_schema_versions": {
                version: {
                    "field_count": len(entry["fields"]),
                    "first_registered": entry["first_seen"],
                    "artifact": entry["artifacts"][0] if entry["artifacts"] else None,
                }
                for version, entry in registry_schema_history().items()
            },
            "context_skip_log": {"path": CONTEXT_SKIP_LOG, "features_logged": len(skip_index["by_feature"])},
        },
        "schema_versions_without_registered_artifact": sorted(
            v for v in ("v2.1", "v2.2", "v2.3") if v not in versions
        ),
        "snapshot_fields": fields,
        "context_features": context_fields,
    }


def write_provenance_report(path=PROVENANCE_REPORT_PATH, db_path=PICKS_DB):
    report = build_provenance_report(db_path=db_path)
    target = _abs(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, default=str))
    return report, str(path)


def main():
    report, path = write_provenance_report()
    print(f"wrote {path}")
    print(f"snapshot fields analysed: {len(report['snapshot_fields'])}")
    print(f"context features analysed: {len(report['context_features'])}")
    for entry in report["snapshot_fields"]:
        print(
            f"  {entry['field']:<50s} raw_missing={entry['missing_pct_raw']}% "
            f"schema_aware_missing={entry['missing_pct_schema_aware']}% {entry['classification']}"
        )


if __name__ == "__main__":
    main()
