# -*- coding: utf-8 -*-
"""Regression tests for the from_generator (DICOM-JSON / database) input path.

These exercise the converter exactly the way a DB-backed pipeline feeds it:
an async generator of PS3.18 DICOM-JSON dicts (one per instance), no files.
"""
import asyncio
import hashlib
import unittest
from typing import Any, AsyncGenerator

from dicom2fhir.dicom2fhir import from_generator
from dicom2fhir.extensions.extension_PT import (
    RADIONUCLIDE_MAPPING,
    RADIOPHARMACEUTICAL_MAPPING,
)
from dicom2fhir.helpers import prune_empties


def _record(**overrides) -> dict:
    """Minimal DICOM-JSON instance record (PS3.18 native model)."""
    rec = {
        "0020000D": {"vr": "UI", "Value": ["1.2.3.4"]},  # StudyInstanceUID
        "0020000E": {"vr": "UI", "Value": ["1.2.3.4.5"]},  # SeriesInstanceUID
        "00080018": {"vr": "UI", "Value": ["1.2.3.4.5.6"]},  # SOPInstanceUID
        "00080016": {"vr": "UI", "Value": ["1.2.840.10008.5.1.4.1.1.2"]},  # SOPClassUID
        "00080060": {"vr": "CS", "Value": ["CT"]},  # Modality
        "00100020": {"vr": "LO", "Value": ["PAT123"]},  # PatientID
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": "Doe^Jane^M"}]},  # PatientName
        "00080020": {"vr": "DA", "Value": ["20240101"]},  # StudyDate
        "00080030": {"vr": "TM", "Value": ["120000"]},  # StudyTime
    }
    rec.update(overrides)
    return rec


def _convert(records: list, config: dict | None = None):
    async def gen() -> AsyncGenerator[dict, Any]:
        for r in records:
            yield r

    cfg = {"dicom_timezone": "UTC"}
    cfg.update(config or {})
    return asyncio.run(from_generator(gen(), config=cfg))


def _resources(b, resource_type: str) -> list:
    return [
        e.resource for e in b.entry if e.resource.__resource_type__ == resource_type
    ]


class TestFromGenerator(unittest.TestCase):
    def test_patient_name_pn_regression(self):
        """VR=PN must land as a proper HumanName (not a JSON-dumped dict)."""
        b = _convert([_record()])
        pat = _resources(b, "Patient")[0]
        self.assertEqual(pat.name[0].family, "Doe")
        self.assertIn("Jane", pat.name[0].given)
        self.assertIn("M", pat.name[0].given)

    def test_deterministic_patient_id_convention(self):
        """Patient.id = sha256('Patient' + PatientID) - external seeders rely on it."""
        b = _convert([_record()])
        pat = _resources(b, "Patient")[0]
        expected = hashlib.sha256("PatientPAT123".encode()).hexdigest()
        self.assertEqual(pat.id, expected)

    def test_series_device_performer(self):
        """series.performer.actor -> Device (MII must-support element)."""
        b = _convert([_record()])
        study = _resources(b, "ImagingStudy")[0]
        device = _resources(b, "Device")[0]
        performer_ref = study.series[0].performer[0].actor.reference
        self.assertEqual(performer_ref, f"Device/{device.id}")

    def test_endpoint_emission_config_gated(self):
        cfg = {"generator": {"endpoint": {"dicomweb_base_url": "https://dicom.example/aets/FMX/"}}}
        b = _convert([_record()], cfg)
        endpoints = _resources(b, "Endpoint")
        self.assertEqual(len(endpoints), 1)
        ep = endpoints[0]
        self.assertEqual(ep.address, "https://dicom.example/aets/FMX")
        # referenced-before-referencing: Endpoint is the FIRST entry
        self.assertEqual(b.entry[0].resource.__resource_type__, "Endpoint")
        study = _resources(b, "ImagingStudy")[0]
        self.assertEqual(study.endpoint[0].reference, f"Endpoint/{ep.id}")

    def test_no_endpoint_by_default(self):
        b = _convert([_record()])
        self.assertEqual(_resources(b, "Endpoint"), [])
        study = _resources(b, "ImagingStudy")[0]
        self.assertFalse(study.endpoint)

    def test_reason_code_from_sequence_items(self):
        rec = _record(**{
            "0040A370": {  # ReferencedRequestSequence
                "vr": "SQ",
                "Value": [
                    {"00401002": {"vr": "LO", "Value": ["Verdacht auf Pneumonie"]}},
                ],
            }
        })
        b = _convert([rec])
        study = _resources(b, "ImagingStudy")[0]
        self.assertTrue(study.reasonCode)
        self.assertEqual(study.reasonCode[0].text, "Verdacht auf Pneumonie")

    def test_add_instances_nested_config(self):
        """The flag is read via a dot-path lookup and must be passed NESTED."""
        cfg = {"generator": {"imaging_study": {"add_instances": True}}}
        b = _convert([_record()], cfg)
        study = _resources(b, "ImagingStudy")[0]
        self.assertEqual(len(study.series[0].instance), 1)
        self.assertEqual(study.series[0].instance[0].uid, "1.2.3.4.5.6")
        # default: counts only, no embedded instances
        b2 = _convert([_record()])
        self.assertFalse(_resources(b2, "ImagingStudy")[0].series[0].instance)
        self.assertEqual(_resources(b2, "ImagingStudy")[0].numberOfInstances, 1)

    def test_pt_radiopharmaceutical_mapping_is_distinct(self):
        """Regression: the radiopharmaceutical lookup must not be the radionuclide table."""
        self.assertFalse(RADIOPHARMACEUTICAL_MAPPING.equals(RADIONUCLIDE_MAPPING))

    def test_duplicate_sop_instance_does_not_crash(self):
        """Duplicate SOPInstanceUID input: first wins, no exception (the old
        code called .as_json() on a plain dict here and crashed)."""
        b = _convert([_record(), _record()])
        study = _resources(b, "ImagingStudy")[0]
        self.assertEqual(study.numberOfInstances, 1)

    def test_from_directory_accepts_iterable_of_dicts(self):
        """The iterable branch used to return an un-awaited coroutine fed with
        a plain list; it must behave like from_generator."""
        from dicom2fhir.dicom2fhir import from_directory

        b = asyncio.run(from_directory([_record()], config={"dicom_timezone": "UTC"}))
        self.assertEqual(len(_resources(b, "ImagingStudy")), 1)
        self.assertEqual(len(_resources(b, "Patient")), 1)

    def test_malformed_patient_name_omits_empty_components(self):
        """A malformed/empty PatientName must omit components, not emit them
        empty: family="" and given=[] are not meaningful values, and an empty
        string survives a None/{}/[]-based prune."""
        from dicom2fhir.dicom2patient import dicom_name_to_fhir

        for raw in ("", "^^^^"):
            self.assertEqual(
                dicom_name_to_fhir(raw).model_dump(exclude_none=True), {},
                f"expected no components for PatientName {raw!r}",
            )

        # Partial names keep what is present and drop what is not.
        self.assertEqual(
            dicom_name_to_fhir("^Given").model_dump(exclude_none=True),
            {"given": ["Given"]},
        )
        self.assertEqual(
            dicom_name_to_fhir("Doe^John^Q^Dr^Jr").model_dump(exclude_none=True),
            {"family": "Doe", "given": ["John", "Q"], "prefix": ["Dr"], "suffix": ["Jr"]},
        )

    def test_prune_empties(self):
        pruned = prune_empties(
            {"a": [], "b": {}, "c": None, "d": 0, "e": False, "f": "", "g": [None, {}, 1]}
        )
        self.assertEqual(pruned, {"d": 0, "e": False, "f": "", "g": [1]})


if __name__ == "__main__":
    unittest.main()
