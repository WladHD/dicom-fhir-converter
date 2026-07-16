from dicom2fhir.dicom2fhirutils import gen_extension, add_extension_value
from dicom2fhir.helpers import get_or

EXTENSION_REASON_URL = "https://www.medizininformatik-initiative.de/fhir/ext/modul-bildgebung/StructureDefinition/mii-ex-bildgebung-bildgebungsgrund"


def _reason_text(ds):
    if not ds.non_empty("RequestAttributesSequence"):
        return None
    reason = ds.RequestAttributesSequence[0].get("ReasonForTheRequestedProcedure", None)
    if reason is None:
        return None
    text = str(reason.value) if hasattr(reason, "value") else str(reason)
    return text if text.strip() else None


def create_extension(ds, config: dict | None = None):
    reason_text = _reason_text(ds)
    if reason_text is None:
        return None

    # The SD defines mii-ex-bildgebung-bildgebungsgrund as a SIMPLE extension
    # (Extension.value[x]: string). The legacy output nested an 'imagingReason'
    # sub-extension instead - kept as the default for output stability; the
    # SD-conformant simple shape is emitted with the experimental MII fixes.
    if get_or(config or {}, "generator.mii.experimental_fixes", False):
        e = gen_extension(url=EXTENSION_REASON_URL)
        e.valueString = reason_text
        return e

    extension_reason = gen_extension(url=EXTENSION_REASON_URL)
    extension_r = gen_extension(url="imagingReason")
    if add_extension_value(
        e=extension_r,
        url="imagingReason",
        value=reason_text,
        system=None,
        unit=None,
        type="string",
    ):
        extension_reason.extension = [extension_r]
        return extension_reason
    return None
