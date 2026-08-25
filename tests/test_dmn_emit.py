"""Serialization and structural validation tests for DMN 1.3 emission."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from tests.test_dmn_builder import _ir
from utils.dmn_builder import DmnBuildError
from utils.dmn_emit import emit_dmn, validate_dmn


def test_emit_is_deterministic_and_structurally_valid():
    first = emit_dmn(_ir())
    second = emit_dmn(_ir())
    assert first == second
    assert first.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    assert validate_dmn(first) == []


def test_validator_rejects_wrong_namespace_and_entry_mismatch():
    wrong_namespace = b'<definitions xmlns="urn:wrong"><decision /></definitions>'
    assert validate_dmn(wrong_namespace) == ["root must be DMN 1.3 definitions"]
    root = ET.fromstring(emit_dmn(_ir()))
    table = next(node for node in root.iter() if node.tag.endswith("decisionTable"))
    rule = next(node for node in table if node.tag.endswith("rule"))
    input_entry = next(node for node in rule if node.tag.endswith("inputEntry"))
    rule.remove(input_entry)
    errors = validate_dmn(ET.tostring(root, encoding="utf-8"))
    assert any("inputEntry count mismatch" in error for error in errors)


def test_invalid_ir_is_refused_before_xml_emission():
    with pytest.raises(DmnBuildError, match="INVALID_IR"):
        emit_dmn({"rules": []})


def test_unproved_real_smoke_tables_are_not_emitted():
    with pytest.raises(DmnBuildError, match="UNPROVED_TABLE_POLICY"):
        emit_dmn(_ir(proof_status="unknown"))
