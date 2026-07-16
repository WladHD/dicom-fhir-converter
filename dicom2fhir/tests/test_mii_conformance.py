# -*- coding: utf-8 -*-
"""Validate emitted resources against the REAL MII StructureDefinitions.

The `kerndatensatz-bildgebung` package (tag v2026.0.0) StructureDefinitions are
vendored under tests/resources/mii/. Instead of asserting hardcoded strings,
these tests derive the expectations from the SDs themselves:

- every Meta.profile canonical must resolve to a vendored SD (right version),
- complex-extension children must use the sub-extension urls (fixedUri) the SD
  defines, with the value[x] type the SD allows,
- profile-required (min>=1) top-level elements must be present,
- reference-target constraints (Observation.partOf) must hold.
"""
import json
import re
import unittest
from pathlib import Path

from dicom2fhir.tests.test_from_generator import _convert, _record, _resources

MII_DIR = Path(__file__).parent / "resources" / "mii"

VALUE_KEY_TO_TYPE = {
    "valueQuantity": "Quantity",
    "valueCodeableConcept": "CodeableConcept",
    "valueString": "string",
    "valueBoolean": "boolean",
    "valueReference": "Reference",
    "valueDateTime": "dateTime",
}


def load_sd(slug: str) -> dict:
    return json.loads((MII_DIR / f"StructureDefinition-{slug}.json").read_text())


def all_sds() -> list[dict]:
    return [json.loads(p.read_text()) for p in MII_DIR.glob("StructureDefinition-*.json")]


def extension_slices(sd: dict) -> dict:
    """{sub-extension url (fixedUri): set of allowed value[x] type codes}."""
    slices: dict = {}
    for e in sd["differential"]["element"]:
        eid = e["id"]
        m = re.match(r"^Extension\.extension:([^.]+)\.url$", eid)
        if m and "fixedUri" in e:
            slices.setdefault(m.group(1), {})["url"] = e["fixedUri"]
        m = re.match(r"^Extension\.extension:([^.]+)\.value\[x\](:.*)?$", eid)
        if m and e.get("type"):
            entry = slices.setdefault(m.group(1), {})
            entry.setdefault("types", set()).update(t["code"] for t in e["type"])
    return {
        v["url"]: v.get("types", set())
        for v in slices.values()
        if "url" in v
    }


def top_value_types(sd: dict) -> set:
    """Allowed types of Extension.value[x] for SIMPLE extensions."""
    for e in sd["differential"]["element"]:
        if e["id"] == "Extension.value[x]" and e.get("type"):
            return {t["code"] for t in e["type"]}
    return set()


def assert_extension_conforms(testcase, ext: dict, sd: dict):
    """ext: serialized parent extension dict; sd: its StructureDefinition."""
    testcase.assertEqual(ext["url"], sd["url"])
    slices = extension_slices(sd)
    if not slices:
        # SIMPLE extension: value[x] directly, no sub-extensions allowed.
        allowed = top_value_types(sd)
        testcase.assertTrue(allowed, f"{sd['name']}: neither slices nor value[x] types parsed")
        testcase.assertFalse(
            ext.get("extension"),
            f"{sd['name']} is a simple extension - sub-extensions are not allowed",
        )
        value_keys = [k for k in ext if k.startswith("value")]
        testcase.assertEqual(len(value_keys), 1, f"{sd['name']}: expected exactly one value[x]")
        testcase.assertIn(VALUE_KEY_TO_TYPE.get(value_keys[0]), allowed)
        return
    for child in ext.get("extension", []):
        testcase.assertIn(
            child["url"],
            slices,
            f"sub-extension '{child['url']}' not defined by {sd['name']} "
            f"(defined: {sorted(slices)})",
        )
        allowed = slices[child["url"]]
        if not allowed:
            continue  # SD does not constrain the value type in its differential
        value_keys = [k for k in child if k.startswith("value")]
        testcase.assertEqual(len(value_keys), 1, f"{child['url']}: expected exactly one value[x]")
        emitted_type = VALUE_KEY_TO_TYPE.get(value_keys[0])
        testcase.assertIn(
            emitted_type,
            allowed,
            f"{child['url']}: emitted {value_keys[0]} but SD allows {sorted(allowed)}",
        )


def serialized(b) -> dict:
    return json.loads(b.model_dump_json())


def entry_resources(bundle_dict: dict, resource_type: str) -> list[dict]:
    return [
        e["resource"]
        for e in bundle_dict.get("entry", [])
        if e["resource"]["resourceType"] == resource_type
    ]


def find_ext(resource: dict, url: str) -> dict | None:
    for ext in resource.get("extension", []) or []:
        if ext["url"] == url:
            return ext
    return None


class TestMIIConformance(unittest.TestCase):
    def test_emitted_profiles_resolve_to_package(self):
        """Every Meta.profile canonical must exist in the MII package; the
        experimental pin must match the package version exactly."""
        sd_urls = {sd["url"]: sd["version"] for sd in all_sds()}
        rec = _record(**{"00101030": {"vr": "DS", "Value": [70.5]}})  # + Observation

        b = serialized(_convert([rec]))
        for rtype in ("ImagingStudy", "Device", "Observation"):
            for res in entry_resources(b, rtype):
                for profile in res["meta"]["profile"]:
                    self.assertIn(profile.split("|")[0], sd_urls, f"{rtype}: unknown canonical")

        cfg = {"generator": {"mii": {"experimental_fixes": True}}}
        b2 = serialized(_convert([rec], cfg))
        for rtype in ("ImagingStudy", "Device"):
            for res in entry_resources(b2, rtype):
                for profile in res["meta"]["profile"]:
                    url, _, version = profile.partition("|")
                    self.assertIn(url, sd_urls)
                    self.assertEqual(version, sd_urls[url], f"{rtype}: pin != package version")

    def test_ct_extension_conforms_to_sd(self):
        rec = _record(**{
            "00189345": {"vr": "FD", "Value": [3.2]},   # CTDIvol
            "00180060": {"vr": "DS", "Value": [120]},   # KVP
            "00181150": {"vr": "IS", "Value": [500]},   # ExposureTime
            "00181152": {"vr": "IS", "Value": [100]},   # Exposure
            "00181151": {"vr": "IS", "Value": [200]},   # XRayTubeCurrent
        })
        sd = load_sd("mii-ex-bildgebung-modalitaet-ct")
        study = entry_resources(serialized(_convert([rec])), "ImagingStudy")[0]
        ext = find_ext(study["series"][0], sd["url"])
        self.assertIsNotNone(ext, "CT extension not emitted")
        self.assertGreaterEqual(len(ext["extension"]), 5)
        assert_extension_conforms(self, ext, sd)

    def test_mr_extension_conforms_to_sd(self):
        rec = _record(**{
            "00080060": {"vr": "CS", "Value": ["MR"]},
            "00180020": {"vr": "CS", "Value": ["SE"]},     # ScanningSequence
            "00180021": {"vr": "CS", "Value": ["NONE"]},   # SequenceVariant
            "00180087": {"vr": "DS", "Value": [3]},        # MagneticFieldStrength
            "00180081": {"vr": "DS", "Value": [15]},       # EchoTime
            "00180080": {"vr": "DS", "Value": [500]},      # RepetitionTime
            "00180082": {"vr": "DS", "Value": [100]},      # InversionTime
            "00181314": {"vr": "DS", "Value": [90]},       # FlipAngle
        })
        sd = load_sd("mii-ex-bildgebung-modalitaet-mr")
        study = entry_resources(serialized(_convert([rec])), "ImagingStudy")[0]
        ext = find_ext(study["series"][0], sd["url"])
        self.assertIsNotNone(ext, "MR extension not emitted")
        assert_extension_conforms(self, ext, sd)

    def test_contrast_extension_conforms_to_sd(self):
        rec = _record(**{"00180010": {"vr": "LO", "Value": ["Ultravist"]}})
        sd = load_sd("mii-ex-bildgebung-kontrastmittel")
        study = entry_resources(serialized(_convert([rec])), "ImagingStudy")[0]
        ext = find_ext(study["series"][0], sd["url"])
        self.assertIsNotNone(ext, "contrast extension not emitted")
        assert_extension_conforms(self, ext, sd)

    def test_instance_details_extension_conforms_to_sd(self):
        rec = _record(**{
            "00280030": {"vr": "DS", "Value": [0.5, 0.6]},           # PixelSpacing
            "00180050": {"vr": "DS", "Value": [1.25]},               # SliceThickness
            "00080008": {"vr": "CS", "Value": ["ORIGINAL", "PRIMARY"]},  # ImageType
        })
        sd = load_sd("mii-ex-bildgebung-instanz-details")
        cfg = {"generator": {"imaging_study": {"add_instances": True}}}
        study = entry_resources(serialized(_convert([rec], cfg)), "ImagingStudy")[0]
        instance = study["series"][0]["instance"][0]
        ext = find_ext(instance, sd["url"])
        self.assertIsNotNone(ext, "instance-details extension not emitted")
        assert_extension_conforms(self, ext, sd)

    def test_reason_extension_conforms_to_sd(self):
        rec = _record(**{
            "00400275": {  # RequestAttributesSequence
                "vr": "SQ",
                "Value": [{"00401002": {"vr": "LO", "Value": ["Kontrolle"]}}],
            }
        })
        sd = load_sd("mii-ex-bildgebung-bildgebungsgrund")
        # default: legacy nested shape frozen for output stability (NOT SD-conformant)
        study_legacy = entry_resources(serialized(_convert([rec])), "ImagingStudy")[0]
        legacy = find_ext(study_legacy, sd["url"])
        self.assertIsNotNone(legacy, "reason extension not emitted")
        self.assertTrue(legacy.get("extension"), "legacy default should keep the nested shape")
        # experimental MII fixes: SD-conformant SIMPLE extension (valueString)
        cfg = {"generator": {"mii": {"experimental_fixes": True}}}
        study = entry_resources(serialized(_convert([rec], cfg)), "ImagingStudy")[0]
        ext = find_ext(study, sd["url"])
        self.assertIsNotNone(ext, "reason extension not emitted (experimental)")
        assert_extension_conforms(self, ext, sd)
        self.assertEqual(ext["valueString"], "Kontrolle")

    def test_required_elements_of_bildgebungsstudie(self):
        """Profile-required (min>=1) top-level ImagingStudy elements are present."""
        sd = load_sd("mii-pr-bildgebung-bildgebungsstudie")
        required = {
            e["path"].split(".", 1)[1]
            for e in sd["differential"]["element"]
            if e.get("min", 0) >= 1
            and e["path"].count(".") == 1
            and "[x]" not in e["path"]
        }
        study = entry_resources(serialized(_convert([_record()])), "ImagingStudy")[0]
        for field in required:
            self.assertIn(field, study, f"profile-required ImagingStudy.{field} missing")

    def test_observation_partof_target_constraint(self):
        """The findings profile constrains partOf to the reading Procedure -
        ImagingStudy is NOT a valid target. The experimental flag complies by
        omitting partOf (0..*)."""
        sd = load_sd("mii-pr-bildgebung-radiologische-beobachtung")
        targets: set = set()
        for e in sd["differential"]["element"]:
            if e["path"] == "Observation.partOf":
                for t in e.get("type", []):
                    targets.update(t.get("targetProfile", []))
        if targets:  # only meaningful if the SD constrains the target
            self.assertFalse(
                any("bildgebungsstudie" in t for t in targets),
                "SD unexpectedly allows ImagingStudy as partOf target",
            )
        rec = _record(**{"00101030": {"vr": "DS", "Value": [70.5]}})
        cfg = {"generator": {"mii": {"experimental_fixes": True}}}
        obs = entry_resources(serialized(_convert([rec], cfg)), "Observation")[0]
        self.assertFalse(obs.get("partOf"), "experimental mode must not emit partOf")


if __name__ == "__main__":
    unittest.main()
