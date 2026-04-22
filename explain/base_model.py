"""BaseModelClass — Python port of src/explain/base_models/BaseModelClass.js

Every simulation model extends this class. The contract matches the JS engine:
- `model_type` (class attribute) names the class and is used by the JSON loader
- `model_interface` (class attribute) declares editable properties (metadata only)
- `__init__(model_ref, name)` stores a reference to the engine and the step size
- `init_model(args)` applies property assignments and instantiates nested components
- `step_model()` gates on `is_enabled and _is_initialized`, then calls `calc_model`
- `calc_model()` is the override point for physiology math
"""

from __future__ import annotations


class BaseModelClass:
    # static properties (class-level metadata)
    model_type: str = ""
    model_interface: list = [
        {"target": "model_type", "type": "string", "build_prop": False,
         "edit_mode": "basic", "readonly": True, "caption": "model type"},
        {"target": "description", "type": "string", "build_prop": True,
         "edit_mode": "basic", "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "edit_mode": "basic", "readonly": False, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        # instance properties every model implements
        self.name = name
        self.description = ""
        self.is_enabled = False
        self.model_type = ""
        self.components: dict = {}

        # internal references
        self._model_engine = model_ref
        self._t: float = model_ref.modeling_stepsize
        self._is_initialized = False

    def init_model(self, args: list):
        """Apply `{key, value}` pairs and recursively instantiate nested components.

        Mirrors BaseModelClass.init_model in the JS engine. `args` is a list of
        `{"key": <str>, "value": <any>}` dicts so that the loader's shape matches
        the JS contract 1:1.
        """
        # import here to avoid a circular import at module-load time
        from .model_index import MODEL_INDEX

        # apply property assignments to self
        for arg in args:
            setattr(self, arg["key"], arg["value"])

        # instantiate nested components (skip if already created)
        for component_name, component_def in self.components.items():
            if component_name not in self._model_engine.models:
                cls = MODEL_INDEX[component_def["model_type"]]
                self._model_engine.models[component_name] = cls(
                    self._model_engine, component_name
                )

        # recursively init nested components
        for component_name, component_def in self.components.items():
            sub_args = [{"key": k, "value": v} for k, v in component_def.items()]
            self._model_engine.models[component_name].init_model(sub_args)

        self._is_initialized = True

    def step_model(self):
        """Called every engine step. Gates on enable + init, then defers to calc_model."""
        if self.is_enabled and self._is_initialized:
            self.calc_model()

    def calc_model(self):
        """Override in subclasses — this is where physiology math lives."""
        pass
