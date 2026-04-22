"""DataCollector — port of src/explain/helpers/DataCollector.js

Captures named model properties at two sample intervals (fast + slow) into
`collected_data` / `collected_data_slow` lists. Watchlist entries resolve
"ModelName.prop" or "ModelName.prop.subprop" into (model_ref, prop1, prop2)
triples at add time.

JS `this.model` is the engine (which carries `.models`, `.modeling_stepsize`).
"""

from __future__ import annotations


class DataCollector:
    def __init__(self, model):
        self.model = model

        self.watch_list = []
        self.watch_list_labels = set()

        self.watch_list_slow = []
        self.watch_list_slow_labels = set()

        self.sample_interval = 0.005
        self.sample_interval_slow = 1.0

        self._interval_counter = 0
        self._interval_counter_slow = 0

        self.modeling_stepsize = self.model.modeling_stepsize

        heart_model = self.model.models.get("Heart")
        self.ncc_ventricular = {
            "label": "Heart.ncc_ventricular",
            "model": heart_model,
            "prop1": "ncc_ventricular",
            "prop2": None,
        }
        self.ncc_atrial = {
            "label": "Heart.ncc_atrial",
            "model": heart_model,
            "prop1": "ncc_atrial",
            "prop2": None,
        }

        self.watch_list.append(self.ncc_atrial)
        self.watch_list.append(self.ncc_ventricular)
        self.watch_list_labels.add(self.ncc_atrial["label"])
        self.watch_list_labels.add(self.ncc_ventricular["label"])

        self.collected_data = []
        self.collected_data_slow = []

    def clear_data(self):
        self.collected_data = []

    def clear_data_slow(self):
        self.collected_data_slow = []

    def clear_watchlist(self):
        self.clear_data()
        self.watch_list = []
        self.watch_list_labels.clear()
        self.watch_list.append(self.ncc_atrial)
        self.watch_list.append(self.ncc_ventricular)
        self.watch_list_labels.add(self.ncc_atrial["label"])
        self.watch_list_labels.add(self.ncc_ventricular["label"])

    def clear_watchlist_slow(self):
        self.clear_data_slow()
        self.watch_list_slow = []
        self.watch_list_slow_labels.clear()

    def get_model_data(self):
        data = self.collected_data
        self.collected_data = []
        return data

    def get_model_data_slow(self):
        data = self.collected_data_slow
        self.collected_data_slow = []
        return data

    def set_sample_interval(self, new_interval=0.005):
        self.sample_interval = new_interval

    def set_sample_interval_slow(self, new_interval=0.005):
        self.sample_interval_slow = new_interval

    def add_to_watchlist(self, properties):
        success = True
        self.clear_data()

        if isinstance(properties, str):
            properties = [properties]

        for prop in properties:
            if prop not in self.watch_list_labels:
                processed_prop = self._find_model_prop(prop)
                if processed_prop is not None:
                    self.watch_list.append(processed_prop)
                    self.watch_list_labels.add(prop)
                else:
                    success = False

        return success

    def add_to_watchlist_slow(self, properties):
        success = True
        self.clear_data_slow()

        if isinstance(properties, str):
            properties = [properties]

        for prop in properties:
            if prop not in self.watch_list_slow_labels:
                processed_prop = self._find_model_prop(prop)
                if processed_prop is not None:
                    self.watch_list_slow.append(processed_prop)
                    self.watch_list_slow_labels.add(prop)
                else:
                    success = False

        return success

    def clean_up(self):
        self.watch_list = [dc for dc in self.watch_list if dc["model"] and dc["model"].is_enabled]
        self.watch_list_labels = set(item["label"] for item in self.watch_list)

    def clean_up_slow(self):
        self.watch_list_slow = [dc for dc in self.watch_list_slow if dc["model"] and dc["model"].is_enabled]
        self.watch_list_slow_labels = set(item["label"] for item in self.watch_list_slow)

    def collect_data(self, model_clock):
        if self._interval_counter >= self.sample_interval:
            self._interval_counter = 0

            data_object = {"time": round(model_clock * 10000) / 10000}

            for parameter in self.watch_list:
                if parameter["model"] and parameter["model"].is_enabled:
                    value = getattr(parameter["model"], parameter["prop1"])
                    if parameter["prop2"] is not None:
                        value = (value.get(parameter["prop2"]) if isinstance(value, dict) else getattr(value, parameter["prop2"], None)) or 0
                    data_object[parameter["label"]] = value

            self.collected_data.append(data_object)

        if self._interval_counter_slow >= self.sample_interval_slow:
            self._interval_counter_slow = 0

            data_object_slow = {"time": round(model_clock * 10000) / 10000}

            for parameter in self.watch_list_slow:
                value = getattr(parameter["model"], parameter["prop1"])
                if parameter["prop2"] is not None:
                    value = (value.get(parameter["prop2"]) if isinstance(value, dict) else getattr(value, parameter["prop2"], None)) or 0
                data_object_slow[parameter["label"]] = value

            self.collected_data_slow.append(data_object_slow)

        self._interval_counter += self.modeling_stepsize
        self._interval_counter_slow += self.modeling_stepsize

    def _find_model_prop(self, prop):
        t = prop.split(".")

        if len(t) == 2:
            if t[0] in self.model.models:
                target = self.model.models[t[0]]
                if hasattr(target, t[1]):
                    r = getattr(target, t[1])
                    return {
                        "label": prop,
                        "model": target,
                        "prop1": t[1],
                        "prop2": None,
                        "ref": r,
                    }

        if len(t) == 3:
            if t[0] in self.model.models:
                target = self.model.models[t[0]]
                if hasattr(target, t[1]):
                    return {
                        "label": prop,
                        "model": target,
                        "prop1": t[1],
                        "prop2": t[2],
                    }

        return None
