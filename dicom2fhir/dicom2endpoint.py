# -*- coding: utf-8 -*-
"""Optional DICOMweb (WADO-RS) Endpoint emission.

Enabled via config key ``generator.endpoint.dicomweb_base_url``. When set, the
bundle gains one Endpoint resource (deterministic id derived from the address,
so every study converted against the same DICOMweb server shares a single
Endpoint and idempotent PUTs are no-ops) and each ImagingStudy references it
via ``ImagingStudy.endpoint``.
"""
import hashlib

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.endpoint import Endpoint

CONNECTION_TYPE_SYS = "http://terminology.hl7.org/CodeSystem/endpoint-connection-type"
PAYLOAD_TYPE_SYS = "http://terminology.hl7.org/CodeSystem/endpoint-payload-type"


def endpoint_id(address: str) -> str:
    """Deterministic, content-addressed Endpoint id for a WADO-RS base URL."""
    return hashlib.sha256(f"Endpoint|wado-rs|{address}".encode("utf-8")).hexdigest()


def build_endpoint_resource(dicomweb_base_url: str) -> Endpoint:
    address = dicomweb_base_url.rstrip("/")
    return Endpoint(
        id=endpoint_id(address),
        status="active",
        connectionType=Coding(
            system=CONNECTION_TYPE_SYS, code="dicom-wado-rs", display="DICOM WADO-RS"
        ),
        payloadType=[
            CodeableConcept(
                coding=[Coding(system=PAYLOAD_TYPE_SYS, code="DICOM", display="DICOM")],
                text="DICOM WADO-RS",
            )
        ],
        address=address,
    )
