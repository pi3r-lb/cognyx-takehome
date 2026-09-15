"""Deterministic BOM quality rules, independent of SQLite and Dagster."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import re

NUMBER = re.compile(r"[+-]?[0-9]+(?:[.,][0-9]+)?\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
UNKNOWN = {"", "null", "none", "n/a", "na", "nan", "unknown", "inconnu", "-"}


def finding(rule, entity, field, message, severity="WARN", status="open", evidence=None):
    return dict(rule=rule, entity_id=entity, field=field, message=message,
                severity=severity, status=status, evidence=evidence or {})


def decimal_text(value):
    return format(value.normalize(), "f")


def normalize(rows, variants):
    normalized, findings, corrections = [], [], []
    variant_map = {}
    for raw in variants:
        v = {k: raw[k].strip() for k in ("variant_id", "name", "root_ref", "root_revision", "snapshot_date")}
        variant_map[v["variant_id"]] = v
        for field in ("variant_id", "root_ref", "root_revision"):
            if not IDENTIFIER.fullmatch(v[field]):
                findings.append(finding("identity", v["variant_id"], field, "Invalid variant/root identity", "ERROR"))
        try:
            date.fromisoformat(v["snapshot_date"])
        except ValueError:
            findings.append(finding("identity", v["variant_id"], "snapshot_date", "Expected ISO date YYYY-MM-DD", "ERROR"))
    for raw in rows:
        rid = raw["row_id"]
        out = {k: raw[k].strip() for k in ("row_id", "variant_id", "parent_ref", "parent_revision", "item_ref",
               "item_revision", "item_type", "description", "supplier", "manufacturer_part_number", "material")}
        out.update(quantity=None, uom=None, length_mm=None, voltage_v=None, included=1, quality_status="checked")
        def change(field, old, new, rule):
            if old != new:
                corrections.append(dict(row_id=rid, field=field, original_value=old, normalized_value=new,
                                        rule=rule, evidence={"row_ids": [rid]}))
        for field, value in list(out.items()):
            if field in raw and isinstance(value, str):
                change(field, raw[field], value, "trim_whitespace")
        for field in ("variant_id", "parent_ref", "parent_revision", "item_ref", "item_revision"):
            if not IDENTIFIER.fullmatch(out[field]) or out[field].lower() in UNKNOWN:
                findings.append(finding("identity", rid, field, "Missing or invalid reference/revision", "ERROR"))
        if out["variant_id"] not in variant_map:
            findings.append(finding("hierarchy", rid, "variant_id", "Variant is absent from variant catalog", "ERROR"))
        if out["item_type"] not in {"assembly", "component"}:
            findings.append(finding("identity", rid, "item_type", "Expected assembly or component", "ERROR"))
        for field in ("supplier", "manufacturer_part_number", "description"):
            if out[field].lower() in UNKNOWN:
                out[field] = None
                findings.append(finding("missing_values", rid, field, f"Unknown {field}; not inferred"))
                change(field, raw[field], None, "unknown_value")
        def number(field, required=False):
            token = raw[field].strip()
            if not token:
                if required:
                    findings.append(finding("missing_values", rid, field, "Quantity is unknown, never zero"))
                return None
            if not NUMBER.fullmatch(token):
                findings.append(finding("numeric_values", rid, field, f"Invalid numeric token: {token!r}", "ERROR"))
                return None
            if sum(c.isdigit() for c in token) > 18:
                findings.append(finding("numeric_values", rid, field, "Numeric precision exceeds the supported 18 digits", "ERROR"))
                return None
            value = Decimal(token.replace(",", "."))
            if value <= 0:
                findings.append(finding("numeric_values", rid, field, "Value must be positive", "ERROR"))
                return None
            return value
        qty = number("quantity", required=True)
        unit = raw["uom"].strip().lower()
        units = {"ea": ("EA", Decimal(1)), "pcs": ("EA", Decimal(1)), "m": ("M", Decimal(1)), "mm": ("M", Decimal("0.001"))}
        if unit not in units:
            findings.append(finding("units", rid, "uom", f"Unsupported quantity unit: {raw['uom']!r}", "ERROR"))
        else:
            out["uom"], factor = units[unit]
            if qty is not None:
                qty *= factor
                if out["uom"] == "EA" and qty != qty.to_integral_value():
                    findings.append(finding("numeric_values", rid, "quantity", "EA quantity must be a whole number", "ERROR"))
                else:
                    out["quantity"] = decimal_text(qty)
        length = number("length")
        length_unit = raw["length_unit"].strip().lower()
        if raw["length"].strip() or length_unit:
            if length_unit not in {"mm", "m"}:
                findings.append(finding("units", rid, "length_unit", "Length requires a supported unit (mm/m)", "ERROR"))
            elif length is not None:
                out["length_mm"] = decimal_text(length * (1000 if length_unit == "m" else 1))
            elif not raw["length"].strip():
                findings.append(finding("missing_values", rid, "length", "Length unit supplied without length"))
        voltage = number("voltage_v")
        out["voltage_v"] = decimal_text(voltage) if voltage is not None else None
        change("quantity", raw["quantity"], out["quantity"], "normalize_quantity")
        change("uom", raw["uom"], out["uom"], "normalize_quantity_unit")
        change("length_mm", raw["length"] + " " + raw["length_unit"], out["length_mm"], "normalize_length")
        change("voltage_v", raw["voltage_v"], out["voltage_v"], "normalize_voltage")
        normalized.append(out)
    return normalized, list(variant_map.values()), findings, corrections


def graph_findings(rows, variants):
    findings = []
    for v in variants:
        selected = [r for r in rows if r["variant_id"] == v["variant_id"] and r["included"]]
        root = (v["root_ref"], v["root_revision"])
        assemblies = {root} | {(r["item_ref"], r["item_revision"]) for r in selected if r["item_type"] == "assembly"}
        graph = defaultdict(set)
        by_parent = defaultdict(list)
        for r in selected:
            parent = (r["parent_ref"], r["parent_revision"])
            child = (r["item_ref"], r["item_revision"])
            graph[parent].add(child)
            by_parent[parent].append(r["row_id"])
            if parent not in assemblies:
                findings.append(finding("hierarchy", r["row_id"], "parent_ref", "Parent is not a root or an assembly of this variant/revision", "ERROR"))
        # Iterative traversal handles cycles without recursion or exponential paths.
        reachable, todo = set(), [root]
        while todo:
            node = todo.pop()
            if node not in reachable:
                reachable.add(node)
                todo.extend(graph.get(node, ()))
        for r in selected:
            if (r["parent_ref"], r["parent_revision"]) not in reachable:
                findings.append(finding("hierarchy", r["row_id"], "parent_ref", "Occurrence is unreachable from the variant root", "ERROR"))
        color = {}
        for start in list(graph):
            stack = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    color[node] = 2
                elif color.get(node) == 1:
                    findings.append(finding("hierarchy", v["variant_id"], "parent_ref", "Cycle in variant BOM", "ERROR", evidence={"row_ids": by_parent[node]}))
                elif color.get(node, 0) == 0:
                    color[node] = 1
                    stack.append((node, True))
                    stack.extend((child, False) for child in graph.get(node, ()))
    return findings


def observation_findings(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["item_ref"], row["item_revision"])].append(row)
    findings = []
    for identity, observations in grouped.items():
        for field in ("length_mm", "voltage_v", "material", "manufacturer_part_number", "uom", "item_type"):
            values = {r[field] for r in observations if r[field] not in (None, "")}
            if len(values) > 1:
                evidence = {"row_ids": [r["row_id"] for r in observations], "values": sorted(values)}
                for row in observations:
                    findings.append(finding("attribute_conflicts", row["row_id"], field,
                                            f"Conflicting observations for {identity[0]} revision {identity[1]}; preserve each value", evidence=evidence))
    return findings
