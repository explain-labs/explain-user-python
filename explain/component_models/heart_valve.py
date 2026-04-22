"""HeartValve — port of src/explain/component_models/HeartValve.js

A HeartValve is a Resistor with a different `model_type` string. The JS source
adds no new properties and no method overrides — the class exists so scenario
JSONs can mark "this resistor represents a heart valve" for the UI / editor /
model organization layers, while sharing all flow math with Resistor.

This port mirrors the JS exactly: subclass Resistor, override `model_type`,
nothing else. If upstream ever adds valve-specific behavior (e.g. a one-way
gate that differs from `no_back_flow`), this class is the place to put it.
"""

from __future__ import annotations

from ..base_models.resistor import Resistor


class HeartValve(Resistor):
    model_type = "HeartValve"
