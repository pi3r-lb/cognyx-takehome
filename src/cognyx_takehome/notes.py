"""Bounded, evidence-preserving extraction; deliberately not general NLP.

Patterns recognize explicit fixture-style declarations, never note IDs. Every
claim retains character offsets. Other prose stays available with partial or
unprocessed coverage; extracted context is not an engineering approval.
"""
import re
from .storage import RULE_VERSION

ALIAS = re.compile(
    r"\ACorrection export\s*:\s*(?P<alias>[A-Z0-9-]+) \(lettre O\) désigne "
    r"(?P<target>[A-Z0-9-]+) révision (?P<revision>[A-Z0-9]+), référence fournisseur "
    r"(?P<mpn>[A-Z0-9-]+)\. Aucun changement technique pour (?P<confirmed_variant>[A-Z0-9-]+)\.\Z")
DUPLICATE = re.compile(
    r"\ALe lot export a répété une ligne de [^.!?]+ de la cassette (?P<parent>[A-Z0-9-]+)\. "
    r"Le plan demande deux [^.!?]+ par cassette, pas quatre\.\Z")
SUPPLIER = re.compile(r"\A(?P<alias>\w+) et (?P<target>\w+) sont deux écritures du même fournisseur "
                      r"fictif dans cet exercice\. Supplier code unchanged\.\Z")
CONTEXT = re.compile(
    r"requires?|exige|besoin|do not|ne pas|no direct substitution|no cross-variant|"
    r"aucune substitution|unverified|reste à vérifier|à vérifier|confirmer|to confirm|"
    r"blank|non renseigné|keep the revision|permet|permits|qualified|qualification", re.I)


def extract(note):
    claims = []
    text = note["text"]
    for kind, pattern in (("reference_alias", ALIAS), ("duplicate_occurrence", DUPLICATE), ("supplier_alias", SUPPLIER)):
        match = pattern.search(text)
        if match:
            claims.append({"kind": kind, "value": match.groupdict(), "start": match.start(), "end": match.end(),
                           "quote": match.group(), "status": "requires_validation", "method": f"explicit-patterns-v{RULE_VERSION}"})
    # Sentence-level passages are context only. Never infer quantities/compatibility.
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        if CONTEXT.search(match.group()):
            claims.append({"kind": "context", "value": {}, "start": match.start(), "end": match.end(),
                           "quote": match.group(), "status": "context_only", "method": f"passage-patterns-v{RULE_VERSION}"})
    return claims, "partial" if claims else "unprocessed"
