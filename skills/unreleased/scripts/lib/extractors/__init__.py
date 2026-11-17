"""Extractor registry. Each extractor: extract(body: str, artifact: Source) -> list[Observation].
Order matters only for de-duplication (first extractor to claim a key wins); classifiers are independent."""
from __future__ import annotations
from importlib import import_module
from schema import Observation, Source

SHAPES = ["gatemap", "catalog", "registry", "proto", "routes", "inline", "calls", "enums", "manifest", "hidden", "strings"]


def extract_all(body: str, artifact: Source, shapes: list[str] | None = None, errors: list[str] | None = None) -> list[Observation]:
    """Every shape over one body. An extractor that raises is recorded in `errors` as "<name>: <error>" and
    skipped — a boundary, not a crash: ten other shapes still read the body."""
    out: list[Observation] = []
    seen: set[tuple[str, str]] = set()
    for name in shapes or SHAPES:
        try:
            mod = import_module(f"extractors.{name}")
        except ModuleNotFoundError:
            continue
        try:
            found = mod.extract(body, artifact)
        except NotImplementedError:
            continue
        except Exception as e:  # noqa: BLE001 — the boundary: one shape's failure is an outcome, not a dead run
            if errors is not None:
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            continue
        for ob in found:
            key = (ob.kind, ob.key)
            if key in seen:
                continue
            seen.add(key); out.append(ob)
    return out


KIND_RANK = {"gate": 0, "inline": 1, "config": 2, "call": 3, "hidden": 4, "manifest": 5, "catalog": 6, "registry": 7, "enum": 8, "proto": 9, "route": 10, "string": 11, "i18n": 12}


def collapse_same_span(observations: list[Observation]) -> list[Observation]:
    """One map read three times (gatemap, registry, inline) is one observation per key: keep the kind that
    says most for each (body, key, offset)."""
    best: dict[tuple[str, str, int], Observation] = {}
    order: list[tuple[str, str, int]] = []
    for o in observations:
        k = (o.source.sha256, o.key, o.source.offset)
        cur = best.get(k)
        if cur is None:
            best[k] = o; order.append(k)
        elif KIND_RANK.get(o.kind, 20) < KIND_RANK.get(cur.kind, 20):
            best[k] = o
    return [best[k] for k in order]
