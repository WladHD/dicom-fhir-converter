# -*- coding: utf-8 -*-
import os
import uuid
import hashlib
from typing import Callable
from dicom2fhir.dicom_json_proxy import DicomJsonProxy

def get_or(d: dict, path: str, default=None):
    """
    Get a value from a nested dictionary using a dot-separated path.
    If the path does not exist, return the default value.
    """
    keys = path.split('.')
    val = d
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val if val is not None else default

def env_or_config(env: str, config_path: str, config: dict):
    """
    Return the value of an environment variable or a configuration key.
    If neither is set raise a ValueError.
    """
    if env in os.environ:
        return os.environ[env]

    val = get_or(config, config_path)
    if val is None:
        raise ValueError(f"Neither environment variable '{env}' nor configuration key '{config_path}' is set.")
    return val

# default id functions
def default_id_function(pepper: str | None = None) -> Callable[[str, DicomJsonProxy], str]:
    """
    Default ID function for FHIR resource id generation.
    Can be customized with a pepper string for additional uniqueness.
    The `extra` parameter can be used to pass additional information to differentiate Resources of the same type.
    """
    def _id(resource_type: str, ds: DicomJsonProxy, extra: str = "") -> str:
        if not isinstance(ds, DicomJsonProxy):
            raise TypeError("Expected a DicomJsonProxy object")

        base_string = f"{pepper or ''}{extra  or ''}{resource_type}"
        if resource_type == "ImagingStudy" and "StudyInstanceUID" in ds:
            base_string = f"{base_string}{ds.StudyInstanceUID}"
        elif resource_type == "Patient" and "PatientID" in ds:
            base_string = f"{base_string}{ds.PatientID}"
        elif resource_type == "Device" and "DeviceSerialNumber" in ds:
            uid = ds.get("DeviceUID") or ''
            ser = ds.get("DeviceSerialNumber") or ''
            mod = ds.get("ManufacturerModelName") or ''
            base_string = f"{base_string}{uid}{ser}{mod}"
        elif resource_type == "Observation":
            uid = ds.StudyInstanceUID if ds.non_empty("StudyInstanceUID") else ""
            study_date = ds.StudyDate if ds.non_empty("StudyDate") else ""
            study_time = ds.StudyTime if ds.non_empty("StudyTime") else ""
            base_string = f"{base_string}{uid}{study_date}{study_time}"
        else:
            return str(uuid.uuid4())

        return hashlib.sha256(base_string.encode("utf-8")).hexdigest()

    return _id

from pydicom import dcmread
import copy
def read_dicom_proxy(file_path, stop_before_pixels=True, force=True):
    ds = dcmread(file_path, stop_before_pixels=stop_before_pixels, force=force)
    ds_copy = copy.deepcopy(ds)

    # Fix Decimal Strings (DS) with commas
    for elem in ds_copy.iterall():
        if elem.VR == "DS":
            if isinstance(elem.value, str):
                elem.value = elem.value.replace(",", ".")
            elif isinstance(elem.value, (list, tuple)):
                elem.value = [v.replace(",", ".") if isinstance(v, str) else v for v in elem.value]

    # Convert to JSON dict
    dicom_json = ds_copy.to_json_dict()

    # Wrap in proxy
    return DicomJsonProxy(dicom_json)


def prune_empties(value):
    """
    Recursively drop None, empty dicts and empty lists from a JSON-like
    structure. fhir.resources serializes optional collections as noise
    (e.g. ``"extension": []``); pruning yields clean output for storage.
    Keeps falsy-but-meaningful values (0, False, "").
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            pv = prune_empties(v)
            if pv is None or pv == {} or pv == []:
                continue
            out[k] = pv
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            pv = prune_empties(v)
            if pv is None or pv == {} or pv == []:
                continue
            out.append(pv)
        return out
    return value


def bundle_to_json_dict(resource, prune: bool = True) -> dict:
    """
    Serialize a fhir.resources resource (e.g. the Bundle returned by
    from_generator) to a plain JSON dict, pruning empty nodes by default.
    """
    import json
    d = json.loads(resource.model_dump_json())
    return prune_empties(d) if prune else d