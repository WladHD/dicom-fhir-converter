# Integration & MII-Conformance Roadmap (WIP)

> **Tracking doc.** Work lands as commits on this branch; checked items are done here.

## Goal

Make `dicom2fhir` able to drive a production FHIR imaging pipeline end to end:

1. Consume DICOM-JSON sourced from a metadata store or DICOMweb backend (not only local files) as a first-class, documented input.
2. Emit resources conformant with the MII *Modul Bildgebung* (`de.medizininformatikinitiative.kerndatensatz.bildgebung`, pin **`2026.0.0`**).
3. Robust, config-driven behaviour for unattended ingestion.
4. Handle large studies efficiently.

## Workstreams

### FHIR correctness
- [x] **Patient.name** — VR=PN lands as a proper `HumanName` (fixed in the json proxy; regression test in `tests/test_from_generator.py`).
- [x] **DICOMweb Endpoint** — config-gated via `generator.endpoint.dicomweb_base_url`: WADO-RS `Endpoint` with deterministic content-addressed id, entry ordered before ImagingStudy, linked from `ImagingStudy.endpoint`. Default off.
- [x] **Instance population** — `generator.imaging_study.add_instances` is the single build path; the key is read via a dot-path lookup and must be passed **nested** (documented + tested).
- [x] **Serialization** — `helpers.prune_empties()` / `helpers.bundle_to_json_dict()` drop `None` / `{}` / `[]` noise.

### MII *Modul Bildgebung* conformance — EXPERIMENTAL, opt-in
Behind `generator.mii.experimental_fixes` (default **off** — default output is unchanged):
- [x] `Observation.partOf` no longer references ImagingStudy (the finding profile constrains `partOf` to a reading Procedure).
- [x] Weight/height vital-signs Observations are emitted **unprofiled** (the `radiologische-beobachtung` findings profile was a mis-profile; `2026.0.0` has no vital-signs model — `2026.1.0`'s `-gewicht`/`-groesse` ImagingStudy extensions are the future home).
- [x] `Meta.profile` canonicals pinned to `|2026.0.0` (ImagingStudy, Device).
- [x] Scope: this converter covers the **Imaging-Metadata** side (ImagingStudy / Device / series / instance). The **Befund/report** side (`DiagnosticReport` and friends) needs a radiology report and is out of scope for a header-only converter.

### Known bug fixes
- [x] `extension_PT` loaded `radionuclide_PT.json` for the radiopharmaceutical lookup (now `radiopharmaceutical_PT.json`).
- [x] `gen_extension`/`add_extension_value` url mismatch at the `pixelSpacing` call sites (emitted output unchanged).
- [x] `ImagingStudy.reasonCode` read the `Reason*` attributes from the top-level dataset while guarded on the sequence item; now read from each `ReferencedRequestSequence` item.
- [x] Removed dead helpers (`calc_gender`, `calc_dob`, `get_patient_resource_ids`).
- [x] `Extension` construction: `Extension(url=...)` directly — newer `fhir_core` releases validate required fields at construction time.

### Packaging & robustness
- [ ] Opt-in lenient-parse preset (pydicom validation posture) for trusted internal data.
- [ ] Optional DB source adapter as an extra (`dicom2fhir[postgres]`): rehydrated DICOM-JSON rows → `AsyncGenerator[dict]`.
- [x] `requirements.txt` aligned with `pyproject.toml`.
- [ ] Refresh `dist/` artefacts.

## Testing
- [x] `tests/test_from_generator.py`: DICOM-JSON input path end to end — PN regression, sha256 id convention, device performer, Endpoint gating + ordering, reasonCode, nested `add_instances`, PT mapping, prune, MII experimental flag.
- [ ] MII validation against `kerndatensatz-bildgebung` `2026.0.0` (external validator).
