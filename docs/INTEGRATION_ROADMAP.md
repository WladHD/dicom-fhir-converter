# Integration & MII-Conformance Roadmap (WIP)

> **Draft / tracking PR.** No code in this commit — this is the plan this branch will be built against.
> Work lands as subsequent commits here; the PR stays in *draft* until the first workstream is ready.

## Goal

Make `dicom2fhir` able to drive a production FHIR imaging pipeline end to end:

1. Consume DICOM-JSON sourced from a metadata store or DICOMweb backend (not only local files) as a first-class, documented input.
2. Emit resources conformant with the MII *Modul Bildgebung* (`de.medizininformatikinitiative.kerndatensatz.bildgebung`, pin **`2026.0.0`**).
3. Robust, config-driven behaviour for unattended ingestion.
4. Handle large studies efficiently.

## Workstreams

### FHIR correctness
- [ ] **Patient.name** — parse VR=PN (`Family^Given^Middle^Prefix^Suffix`) into a proper `HumanName` (confirm current HEAD already covers this; add a regression test).
- [ ] **DICOMweb Endpoint** — optional, config-gated (`dicomweb_base_url`): emit a WADO-RS `Endpoint`, deterministic id, link `ImagingStudy.endpoint`, and order the Endpoint before ImagingStudy in transaction bundles.
- [ ] **Instance population** — make `ImagingStudy.series.instance[]` authoritative via `generator.imaging_study.add_instances` (single build path, no double construction).
- [ ] **Serialization** — optional empty-collection pruning (drop `None` / `{}` / `[]`, e.g. `extension: []`).

### MII *Modul Bildgebung* conformance (pin `2026.0.0`)
- [ ] Fix `Observation.partOf`: the finding profile constrains `partOf` to a reading `Procedure`, not `ImagingStudy` — drop or retarget it.
- [ ] Stop stamping `mii-pr-bildgebung-radiologische-beobachtung` on vital-signs (weight/height) Observations — that profile models findings. Emit plain FHIR vital-signs until the `2026.1.0` `-gewicht` / `-groesse` ImagingStudy extensions are released.
- [ ] Pin every `Meta.profile` to `|2026.0.0`.
- [ ] Document scope: this converter covers the **Imaging-Metadata** side (ImagingStudy / Device / series / instance). The **Befund/report** side (`DiagnosticReport` and friends) needs a radiology report and is out of scope for a header-only converter.

### Known bug fixes
- [ ] `extension_PT` loads `radionuclide_PT.json` for the radiopharmaceutical lookup (should be `radiopharmaceutical_PT.json`).
- [ ] `add_extension_value` overwrites the `url` set by `gen_extension` (visible in the `pixelSpacing` sub-extensions).
- [ ] `ImagingStudy.reasonCode` gating is inconsistent (guarded by `ReferencedRequestSequence` presence but reads top-level `ReasonFor…`).
- [ ] Remove dead helpers (`calc_gender`, `calc_dob`, `get_patient_resource_ids`).

### Packaging & robustness
- [ ] Opt-in lenient-parse preset (pydicom validation posture) for trusted internal data.
- [ ] Optional DB source adapter as an extra (`dicom2fhir[postgres]`): rehydrated DICOM-JSON rows → `AsyncGenerator[dict]`.
- [ ] Refresh `dist/` artefacts; align `requirements.txt` with `pyproject.toml`.

### Efficiency
- [ ] True single-pass streaming (cursor → bundle) to cap memory on large studies.
- [ ] Single serialization pass (`model_dump(exclude_none=True)`) instead of serialize → parse → rebuild → serialize.

## Testing
- [ ] Golden-file tests: DICOM-JSON in → expected bundle out.
- [ ] Per-modality extension coverage.
- [ ] MII validation against `kerndatensatz-bildgebung` `2026.0.0`.
