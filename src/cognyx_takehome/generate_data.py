"""Generate the fictional pilot inputs and a separate evaluation oracle.

Python 3.9 standard library only. This authors fixtures, not an analysis engine.
All engineering values, names, identifiers, and notes below are invented.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path


VARIANTS = (
    ("REG-A", "Regional standard", "SYN-TRAIN-A"),
    ("REG-B", "Regional extended", "SYN-TRAIN-B"),
    ("REG-C", "Regional cold-climate", "SYN-TRAIN-C"),
)
BOM_FIELDS = (
    "row_id", "source_export_id", "source_line", "variant_id",
    "parent_ref", "parent_revision", "item_ref", "item_revision", "item_type",
    "description", "quantity", "uom", "supplier", "manufacturer_part_number",
    "length", "length_unit", "material", "voltage_v",
)


def part(ref, en, fr, supplier, *, length="", material="", voltage="", rev="A"):
    return dict(ref=ref, en=en, fr=fr, supplier=supplier, length=length,
                material=material, voltage=voltage, rev=rev, mpn="SYN-MPN-" + ref)


def fixtures():
    """Return authored source tables and expected findings in a stable order."""
    lumen, air, elec, fix = "Synthelume", "FictiAir", "DemoVolt", "MockFix"
    bolt = part("FIX-M6-20", "M6 mounting bolt", "Vis de fixation M6", fix,
                length="20", material="steel")
    washer = part("FIX-W6", "M6 washer", "Rondelle M6", fix, material="steel")
    nut = part("FIX-N6", "M6 nut", "Écrou M6", fix, material="steel")
    light = part("LGT-100", "Cabin lighting module", "Module éclairage cabine", lumen,
                 length="1200", material="aluminium", voltage="24")
    comfort_light = part("LGT-200", "Cabin lighting module", "Module éclairage cabine", lumen,
                         length="1200", material="aluminium", voltage="24")
    hvac = part("FLT-100", "HVAC filter cassette", "Cassette filtre CVC", air,
                length="600", material="aluminium")
    service_hvac = part("FLT-150", "HVAC filter cassette", "Cassette filtre CVC", air,
                        length="600", material="aluminium")
    cold_hvac = part("FLT-200", "HVAC filter cassette", "Cassette filtre CVC", air,
                     length="600", material="aluminium")
    cabinet = part("CAB-240", "Passenger information cabinet", "Coffret information voyageurs",
                   elec, length="600", material="aluminium", voltage="24")
    vented_cabinet = part("CAB-245", "Passenger information cabinet", "Coffret information voyageurs",
                          elec, length="600", material="aluminium", voltage="24")
    high_cabinet = part("CAB-110", "Passenger information cabinet", "Coffret information voyageurs",
                        elec, length="600", material="aluminium", voltage="110")
    lighting = [
        (part("LGT-RAIL", "Light extrusion", "Profilé éclairage", lumen, length="1200", material="aluminium"), "1", "EA"),
        (part("LGT-LED", "LED board", "Carte LED", lumen, voltage="24"), "2", "EA"),
        (part("LGT-DRV", "LED driver", "Pilote LED", elec, voltage="24"), "1", "EA"),
        (part("LGT-DIFF", "Light diffuser", "Diffuseur éclairage", lumen, length="1200", material="polycarbonate"), "1", "EA"),
        (part("LGT-END", "End cap", "Embout", lumen, material="polycarbonate"), "2", "EA"),
        (part("LGT-CLIP", "Mounting clip", "Clip de fixation", fix, material="steel"), "4", "EA"),
        (part("CBL-2C", "Two-core cable", "Câble deux conducteurs", elec), "2.5", "M"),
        (part("CON-2P", "Two-pole connector", "Connecteur deux pôles", elec), "2", "EA"),
        (bolt, "4", "EA"), (washer, "4", "EA"), (nut, "4", "EA"),
        (part("LGT-LABEL", "Lighting identification label", "Étiquette éclairage", lumen), "1", "EA"),
    ]
    filtration = [
        (part("FLT-FRAME", "Filter frame", "Cadre filtre", air, length="600", material="aluminium"), "1", "EA"),
        (part("FLT-MEDIA", "Standard filter insert", "Élément filtrant standard", air), "1", "EA"),
        (part("FLT-GASK-EP", "Filter gasket", "Joint filtre", air, material="EPDM"), "2.4", "M"),
        (part("FLT-GRID", "Filter support grid", "Grille support filtre", air, length="600", material="steel"), "1", "EA"),
        (part("FLT-LATCH", "Filter latch", "Loquet filtre", fix), "2", "EA"),
        (part("FLT-HINGE", "Filter hinge", "Charnière filtre", fix), "2", "EA"),
        (part("FLT-HANDLE", "Filter handle", "Poignée filtre", fix), "1", "EA"),
        (bolt, "8", "EA"), (washer, "8", "EA"), (nut, "8", "EA"),
        (part("FLT-LABEL", "Airflow direction label", "Étiquette sens du flux", air), "1", "EA"),
        (part("FLT-STOP", "Filter end stop", "Butée filtre", air), "2", "EA"),
    ]
    cabinets = [
        (part("CAB-BOX", "Cabinet enclosure", "Boîtier coffret", elec, length="600", material="aluminium"), "1", "EA"),
        (part("CAB-PS24", "Cabinet power module", "Module alimentation coffret", elec, voltage="24"), "1", "EA"),
        (part("CAB-CPU", "Information controller", "Contrôleur information", elec, voltage="24"), "1", "EA"),
        (part("CAB-SW", "Network switch", "Commutateur réseau", elec, voltage="24"), "1", "EA"),
        (part("CAB-TERM", "Input terminal block", "Bornier entrée", elec), "1", "EA"),
        (part("CAB-FUSE", "Input fuse holder", "Porte-fusible entrée", elec), "1", "EA"),
        (part("CAB-H24", "Cabinet input harness", "Faisceau entrée coffret", elec, voltage="24"), "1", "EA"),
        (part("CAB-FAN", "Cabinet fan", "Ventilateur coffret", elec, voltage="24"), "1", "EA"),
        (part("CAB-DIN", "DIN mounting rail", "Rail de montage DIN", fix, length="500", material="steel"), "1", "EA"),
        (bolt, "6", "EA"), (washer, "6", "EA"), (nut, "6", "EA"),
    ]
    rows, variants, ids = [], [], {}

    for index, (variant, name, root) in enumerate(VARIANTS):
        variants.append(dict(variant_id=variant, name=name, root_ref=root,
                             root_revision="A", snapshot_date="2026-09-01",
                             scope="Selected interior sub-assemblies only; not a complete train BOM",
                             data_status="synthetic"))
        assemblies = [("lighting", (light, light, comfort_light)[index], lighting, (12, 16, 12)[index]),
                      ("filtration", (hvac, service_hvac, cold_hvac)[index], filtration, (2, 3, 2)[index]),
                      ("cabinet", (cabinet, vented_cabinet, high_cabinet)[index], cabinets, 1)]
        source_line = 2

        def add(item, parent, quantity, unit, kind, key):
            nonlocal source_line
            row_id = "{}-{:03d}".format(variant, source_line - 1)
            row = dict(zip(BOM_FIELDS, [
                row_id, "SYNTHETIC-PLM-" + variant, source_line, variant,
                parent, "A", item["ref"], item["rev"], kind,
                item["fr"] if index == 1 else item["en"], quantity,
                "pcs" if index == 1 and unit == "EA" else unit,
                item["supplier"], item["mpn"], item["length"],
                "mm" if item["length"] else "", item["material"], item["voltage"],
            ]))
            rows.append(row)
            ids[variant, key] = row_id
            source_line += 1
            return row

        for family, assembly, children, count in assemblies:
            raw_parent = " LGT-1O0 " if index == 1 and family == "lighting" else assembly["ref"]
            top = add(assembly, root, str(count), "EA", "assembly", family)
            top["item_ref"] = raw_parent
            for original, quantity, unit in children:
                item = original.copy()
                if index == 2 and item["ref"] == "LGT-DIFF":
                    item.update(ref="LGT-DIFF-OP", mpn="SYN-MPN-LGT-DIFF-OP",
                                en="Opal light diffuser")
                if index == 1 and item["ref"] == "FLT-HANDLE":
                    item.update(ref="FLT-HANDLE-F", mpn="SYN-MPN-FLT-HANDLE-F",
                                fr="Poignée filtre rabattable")
                if index == 1 and item["ref"] == "CAB-BOX":
                    item.update(ref="CAB-BOX-VENT", mpn="SYN-MPN-CAB-BOX-VENT",
                                fr="Boîtier coffret à porte ventilée")
                if index == 2 and item["ref"] == "FLT-MEDIA":
                    item.update(ref="FLT-MEDIA-C", mpn="SYN-MPN-FLT-MEDIA-C",
                                en="Cold-climate filter insert")
                if index == 2 and item["ref"] == "FLT-GASK-EP":
                    item.update(ref="FLT-GASK-SI", mpn="SYN-MPN-FLT-GASK-SI", material="silicone")
                if index == 2 and item["ref"] in ("CAB-PS24", "CAB-H24"):
                    item.update(ref=item["ref"].replace("24", "110"),
                                mpn=item["mpn"].replace("24", "110"), voltage="110")
                if index == 2 and item["ref"] == "CAB-FAN":
                    item["rev"] = "B"
                row = add(item, raw_parent, quantity, unit, "component", family + "/" + original["ref"])
                if index == 1 and original["ref"] == "CBL-2C":
                    row.update(quantity="2500", uom="mm")
                if index == 1 and original["ref"] == "FLT-GASK-EP":
                    row.update(quantity="2,4", uom="m")
                if index == 1 and original["ref"] == "FLT-FRAME":
                    row.update(length="0,6", length_unit="m")
                if index == 1 and original["supplier"] == air:
                    row["supplier"] = "FICTIAIR "
                if index == 2 and family == "cabinet" and original["ref"] == "FIX-M6-20":
                    row["length"] = "25"
                if index == 2 and original["ref"] == "CAB-SW":
                    row["supplier"] = ""
                if index == 1 and original["ref"] == "CAB-TERM":
                    row["quantity"] = ""
        if index == 1:
            original = next(r for r in rows if r["row_id"] == ids[variant, "filtration/FLT-LATCH"])
            duplicate = original.copy()
            duplicate.update(row_id="REG-B-040", source_line=source_line)
            rows.append(duplicate)
            ids[variant, "duplicate"] = duplicate["row_id"]

    # Notes are source evidence, not machine-readable answers. Identity corrections
    # and constraints appear here as they might in a fictional engineering memo.
    note_specs = [
        ("REG-A", "LGT-100", "A", "en", "REG-A uses LGT-100 rev A with a clear diffuser. Input 24 V DC; mounting pitch 1100 mm; two LED boards per module. Nominal output 1800 lm, measured glare index 21 in the fictional reference test. Module count is per train; child quantities are per module."),
        ("REG-B", " LGT-1O0 ", "A", "fr", "Correction export : LGT-1O0 (lettre O) désigne LGT-100 révision A, référence fournisseur SYN-MPN-LGT-100. Aucun changement technique pour REG-B."),
        ("REG-B", "CBL-2C", "A", "mixed", "Longueur coupée : 2500 mm par module, soit 2,5 m. Same two-core cable as REG-A; do not interpret 2500 as metres."),
        ("REG-A", "FLT-100", "A", "fr", "REG-A utilise FLT-100 indice A : cadre 600 mm, poignée fixe dépassant de 35 mm, joint EPDM. Domaine de qualification synthétique : -10 à +45 °C. Dégagement de maintenance REG-A : 50 mm ; débit requis 800 m3/h."),
        ("REG-B", "FLT-FRAME", "A", "fr", "Le cadre de 0,6 m est le cadre de 600 mm ; la cote est une longueur unitaire et non une quantité à commander."),
        ("REG-C", "FLT-200", "A", "en", "REG-C requires operation down to -25 C and 800 m3/h airflow. FLT-200 has a 600 mm envelope and interface IF-F600, also used by FLT-100/150. Silicone gasket and cold-climate insert qualified for -30 to +45 C in this synthetic case. Existing airflow test covers REG-C ducting only; pressure drop in REG-A/B ducting is unverified. No cross-variant substitution released."),
        ("REG-C", "FLT-GASK-SI", "A", "fr", "Joint silicone prévu dans la cassette climat froid. Ne pas remplacer par le joint EPDM sur la seule base de la longueur."),
        ("REG-B", "FLT-GASK-EP", "A", "fr", "Consommation par cassette : 2,4 m de joint EPDM. La virgule est le séparateur décimal de cet export."),
        ("REG-A", "CAB-240", "A", "en", "REG-A uses CAB-240: 24 V DC input, 600 mm enclosure, vehicle interface IF-PIS24, sealed door. Controller and switch dissipate 45 W at full load in the synthetic design. REG-A requires a sealed door due to its cleaning regime."),
        ("REG-C", "CAB-110", "A", "mixed", "Entrée coffret : 110 V DC; internal controller bus: 24 V DC after conversion. Same enclosure length as CAB-240, but input power module and harness differ. No direct substitution."),
        ("REG-C", "FIX-M6-20", "A", "fr", "Écart à vérifier : la ligne de vis du coffret indique 25 mm, alors que la référence FIX-M6-20 et la fiche article indiquent 20 mm. Confirmer la vis montée ; ne pas corriger la cote automatiquement."),
        ("REG-C", "CAB-FAN", "B", "en", "Fan revision B retains 24 V supply but reverses connector pin order relative to revision A. Keep the revision in the identity; replacement requires wiring review."),
        ("REG-C", "CAB-SW", "A", "fr", "Fournisseur du commutateur non renseigné dans cet export. Référence fabricant conservée ; confirmer la source approuvée avant achat."),
        ("REG-B", "CAB-TERM", "A", "en", "Terminal-block quantity is blank in the extract. Blank means unknown, not zero; verify the released cabinet drawing."),
        ("REG-B", "FLT-LATCH", "A", "fr", "Le lot export a répété une ligne de loquet de la cassette FLT-150. Le plan demande deux loquets par cassette, pas quatre."),
        ("REG-B", "FLT-150", "A", "mixed", "FICTIAIR et FictiAir sont deux écritures du même fournisseur fictif dans cet exercice. Supplier code unchanged."),
        ("REG-A", "FIX-M6-20", "A", "en", "The same mounting bolt appears under lighting, filtration and the cabinet. Each parent has its own required quantity; repeated use under different parents is intentional."),
        ("REG-C", "LGT-200", "A", "fr", "REG-C utilise LGT-200, diffuseur opale distinct de LGT-100. Alimentation 24 V DC, entraxe 1100 mm. Essai synthétique : 1600 lm et indice d'éblouissement 18. REG-C exige au moins 1500 lm et un indice au plus 19 ; REG-A/B exigent au moins 1500 lm et un indice au plus 22. La photométrie dans les intérieurs REG-A/B reste à vérifier ; aucune substitution libérée."),
        ("REG-B", "FLT-150", "A", "fr", "REG-B utilise FLT-150, poignée rabattable : saillie repliée 10 mm, dégagement disponible 20 mm. Interface IF-F600 et filtre/joint identiques à FLT-100. Besoin -10 à +45 °C et 800 m3/h. Aucun essai de manipulation de cette poignée sur REG-A ; aucune substitution libérée."),
        ("REG-B", "CAB-245", "A", "mixed", "CAB-245: 24 V DC, vehicle interface IF-PIS24, porte ventilée; REG-B is a dry protected location and permits either door type. Same 45 W electronics as CAB-240, but enclosed installation bay reaches 45 C. CAB-240 thermal test available only at 35 C ambient. Quantity of terminal block still to confirm. No cross-variant substitution released."),
    ]
    notes = [dict(note_id="NOTE-{:03d}".format(i), source_document="SYNTHETIC-TECH-MEMO-{:03d}".format(i),
                  variant_id=v, applies_to_ref=ref, applies_to_revision=rev, language=lang, text=body)
             for i, (v, ref, rev, lang, body) in enumerate(note_specs, 1)]

    def refs(*keys):
        return [ids[key] for key in keys]

    findings = []

    def expect(key, category, row_ids, note_ids, outcome, **details):
        findings.append(dict(finding_id=key, category=category, row_ids=row_ids,
                             note_ids=note_ids, expected_outcome=outcome, **details))

    expect("F01", "candidate_reuse", refs(("REG-A", "lighting"), ("REG-B", "lighting"), ("REG-C", "lighting")),
           ["NOTE-001", "NOTE-002", "NOTE-018"], "Existing LGT-200 from REG-C could replace LGT-100 in REG-A/B at a future tender: matching mount/supply and nominal optical limits; verify photometry in the target interiors. Distinct diffuser means distinct designs, not an alias.",
           donor_ref="LGT-200", donor_variant="REG-C", target_ref="LGT-100", target_variants=["REG-A", "REG-B"],
           approval_status="not_approved", required_checks=["Target-interior photometry", "Engineering release"])
    expect("F02", "reference_alias", [r["row_id"] for r in rows if r["variant_id"] == "REG-B"
           and " LGT-1O0 " in (r["item_ref"], r["parent_ref"])], ["NOTE-002"],
           "Normalize the explicitly documented alias, including child parent references; join REG-B to the observed lighting reuse group.",
           raw_ref=" LGT-1O0 ", canonical_ref="LGT-100", revision="A")
    expect("F03", "unit_equivalence", refs(("REG-A", "lighting/CBL-2C"), ("REG-B", "lighting/CBL-2C")),
           ["NOTE-003"], "2.5 M and 2500 mm are both 2.5 metres per lighting module.", normalized_quantity="2.5", normalized_uom="m")
    expect("F04", "dimension_equivalence", refs(("REG-A", "filtration/FLT-FRAME"), ("REG-B", "filtration/FLT-FRAME")),
           ["NOTE-005"], "600 mm and 0,6 m are the same item length; neither is an assembly quantity.", normalized_length_mm="600")
    expect("F05", "decimal_comma", refs(("REG-B", "filtration/FLT-GASK-EP")),
           ["NOTE-008"], "Parse 2,4 as 2.4 metres, not 24 or two separate fields.", normalized_quantity="2.4", normalized_uom="m")
    expect("F06", "candidate_reuse", refs(("REG-A", "filtration"), ("REG-C", "filtration")),
           ["NOTE-004", "NOTE-006", "NOTE-007"], "Existing cold-climate FLT-200 could replace FLT-100 in temperate REG-A: interface and temperature range are compatible on paper; verify pressure drop, airflow and sealing in target ducting. This does not authorize the reverse substitution.",
           donor_ref="FLT-200", donor_variant="REG-C", target_ref="FLT-100", target_variants=["REG-A"],
           approval_status="not_approved", required_checks=["Target-duct airflow and pressure drop", "Sealing", "Engineering release"])
    expect("F07", "incompatible_near_match", refs(("REG-A", "cabinet"), ("REG-C", "cabinet")),
           ["NOTE-009", "NOTE-010"], "Keep CAB-240 and CAB-110 separate despite matching descriptions and dimensions; their input voltages and harnesses differ.")
    expect("F08", "conflicting_attribute", refs(("REG-A", "cabinet/FIX-M6-20"), ("REG-C", "cabinet/FIX-M6-20")),
           ["NOTE-011"], "Flag 20 versus 25 mm for the same reference and revision; do not silently overwrite either source value.")
    expect("F09", "revision_difference", refs(("REG-A", "cabinet/CAB-FAN"), ("REG-C", "cabinet/CAB-FAN")),
           ["NOTE-012"], "Preserve revisions A and B as different identities; voltage equality does not establish interchangeability.")
    expect("F10", "missing_supplier", refs(("REG-C", "cabinet/CAB-SW")), ["NOTE-013"],
           "Flag unknown supplier; do not invent an approved source.")
    expect("F11", "missing_quantity", refs(("REG-B", "cabinet/CAB-TERM")), ["NOTE-014"],
           "Preserve unknown quantity and flag it; do not treat blank as zero or automatically fill from another variant.")
    expect("F12", "duplicate_export_row", refs(("REG-B", "filtration/FLT-LATCH"), ("REG-B", "duplicate")),
           ["NOTE-015"], "Retain both source rows as evidence, but count two latches per FLT-150 cassette after resolving the documented duplicate, not four.")
    expect("F13", "supplier_alias", refs(("REG-A", "filtration"), ("REG-B", "filtration/FLT-FRAME")),
           ["NOTE-016"], "Normalize FICTIAIR with trailing whitespace to FictiAir using documented supplier identity.")
    expect("F14", "legitimate_repeated_use", refs(("REG-A", "lighting/FIX-M6-20"), ("REG-A", "filtration/FIX-M6-20"), ("REG-A", "cabinet/FIX-M6-20")),
           ["NOTE-017"], "Do not deduplicate across parents: REG-A uses 12*4 + 2*8 + 1*6 = 70 of this bolt within the selected scope.", total_quantity="70")
    expect("F15", "candidate_reuse", refs(("REG-A", "filtration"), ("REG-B", "filtration")),
           ["NOTE-004", "NOTE-015", "NOTE-019"], "Reuse existing FLT-150 from REG-B as a candidate replacement for FLT-100 in REG-A: shared filter/gasket/interface and a smaller folded handle. Validate maintenance handling in the target bay; resolve the duplicated latch row. These remain distinct assembly references.",
           donor_ref="FLT-150", donor_variant="REG-B", target_ref="FLT-100", target_variants=["REG-A"],
           approval_status="not_approved", required_checks=["Target-bay handle operation", "Duplicate-row resolution", "Engineering release"])
    expect("F16", "candidate_reuse", refs(("REG-A", "cabinet"), ("REG-B", "cabinet")),
           ["NOTE-009", "NOTE-014", "NOTE-020"], "Existing sealed CAB-240 could replace vented CAB-245 in REG-B, which permits either door. Shared input/interface/electronics support investigation, but verify 45 W heat rejection at REG-B's 45 C ambient and resolve the missing terminal quantity. No automatic merge or approved replacement.",
           donor_ref="CAB-240", donor_variant="REG-A", target_ref="CAB-245", target_variants=["REG-B"],
           approval_status="not_approved", required_checks=["Thermal test at 45 C ambient", "Terminal quantity confirmation", "Engineering release"])
    expect("F17", "observed_reuse", refs(("REG-A", "lighting"), ("REG-B", "lighting")),
           ["NOTE-001", "NOTE-002"], "LGT-100 revision A is already used in REG-A/B after resolving the documented alias. This baseline is not a new substitution opportunity.")
    expect("F18", "incompatible_near_match", refs(("REG-A", "lighting"), ("REG-C", "lighting")),
           ["NOTE-001", "NOTE-018"], "Do not propose LGT-100 as a direct replacement for LGT-200 in REG-C: glare index 21 exceeds REG-C's maximum 19, despite matching size and supply.",
           donor_ref="LGT-100", target_ref="LGT-200", target_variants=["REG-C"])
    expect("F19", "incompatible_near_match", refs(("REG-A", "filtration"), ("REG-B", "filtration"), ("REG-C", "filtration")),
           ["NOTE-004", "NOTE-006", "NOTE-019"], "Neither temperate filter cassette meets REG-C's -25 C requirement: the -10 C lower limit rules out direct substitution without redesign/requalification.",
           donor_refs=["FLT-100", "FLT-150"], target_ref="FLT-200", target_variants=["REG-C"])
    expect("F20", "incompatible_near_match", refs(("REG-A", "filtration"), ("REG-B", "filtration")),
           ["NOTE-004", "NOTE-019"], "Do not replace FLT-150 by FLT-100 in REG-B: fixed handle protrudes 35 mm into only 20 mm of available clearance.",
           donor_ref="FLT-100", target_ref="FLT-150", target_variants=["REG-B"])
    expect("F21", "incompatible_near_match", refs(("REG-A", "cabinet"), ("REG-B", "cabinet")),
           ["NOTE-009", "NOTE-020"], "Do not replace CAB-240 by vented CAB-245 in REG-A: that location requires a sealed door. The reverse candidate does not establish symmetric compatibility.",
           donor_ref="CAB-245", target_ref="CAB-240", target_variants=["REG-A"])
    return variants, rows, notes, findings


def write_csv(path, records, fields):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate(output):
    output = Path(output)
    (output / "expected").mkdir(parents=True, exist_ok=True)
    variants, rows, notes, findings = fixtures()
    for name, records, fields in (
        ("variants.csv", variants, list(variants[0])),
        ("bom.csv", rows, BOM_FIELDS),
        ("technical_notes.csv", notes, list(notes[0])),
    ):
        write_csv(output / name, records, fields)
    write_json(output / "expected" / "findings.json", dict(
        data_status="synthetic", purpose="Evaluation oracle only; never an analyzer input",
        exhaustive=False, findings=findings))
    manifest = dict(
        dataset_id="cognyx-synthetic-rail-v2", data_status="synthetic",
        provenance="Original authored fixtures; no Alstom, customer, or third-party dataset rows copied",
        engineering_status="Invented demonstration assumptions; not validated designs or substitution approvals",
        reuse_semantics="All assemblies already exist on their listed variants. A candidate proposes using an existing donor design in another variant at a future tender; it is directional, conditional, and not a part-identity merge or an approved engineering change.",
        scope="Three fictional variants; selected lighting, filtration and information-cabinet sub-assemblies only",
        snapshot_date="2026-09-01", generator="src/cognyx_takehome/generate_data.py",
        generation="Deterministic authored scenarios; no randomness, network, or third-party dependencies",
        csv=dict(encoding="UTF-8", delimiter=",", quotechar='"', header=True, newline="LF", blank="unknown or not applicable, never implicitly zero"),
        identity="Part reference plus revision; preserve raw values and use evidenced alias mapping",
        quantity_semantics="Each row is a direct parent-child edge. Quantity is per one parent assembly, not per train. Root counts scale selected assemblies per train.",
        length_semantics="Length is an item attribute; length_unit does not change quantity/uom",
        voltage_semantics="Nominal item input voltage in V DC; cabinet input may differ from internal component bus voltage",
        source_semantics="source_export_id/source_document identify invented source records. source_line is the line number within the simulated per-variant export including its header, not the combined bom.csv line.",
        deliberate_issues="See evaluation-only expected/findings.json. Findings are scenario checks, not analyzer output or an exhaustive count of affected rows.",
        costs="No costs, savings, or measured customer metrics included",
        files={})
    for name, count in (("variants.csv", len(variants)), ("bom.csv", len(rows)),
                        ("technical_notes.csv", len(notes)), ("expected/findings.json", len(findings))):
        manifest["files"][name] = dict(records=count, sha256=hashlib.sha256((output / name).read_bytes()).hexdigest())
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data"),
                        help="Output directory; replaces this generator's named files (default: data)")
    args = parser.parse_args()
    manifest = generate(args.output)
    print("Generated synthetic dataset in {}: {} BOM rows, {} notes, {} expected findings".format(
        args.output, manifest["files"]["bom.csv"]["records"],
        manifest["files"]["technical_notes.csv"]["records"],
        manifest["files"]["expected/findings.json"]["records"]))


if __name__ == "__main__":
    main()
