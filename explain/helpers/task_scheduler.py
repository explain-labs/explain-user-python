"""TaskScheduler — port of src/explain/helpers/TaskScheduler.js

Three task types:
  type 0: numeric tween (linearly interpolate a property over `it` seconds)
  type 1: immediate primitive swap (boolean/string)
  type 2: deferred function call (`func.apply(model, args)` after `at` seconds)

Task IDs use random numeric suffix to match JS. Tasks are evaluated every
`_task_interval` (15 ms) — not every engine step.
"""

from __future__ import annotations

import random


class TaskScheduler:
    def __init__(self, model_ref):
        self._model_engine = model_ref
        self._t = model_ref.modeling_stepsize
        self._is_initialized = False
        self.is_enabled = True

        self._tasks = {}
        self._task_interval = 0.015
        self._task_interval_counter = 0.0

    def add_function_call(self, new_function_call):
        task_id = int(random.random() * 10000)
        id_ = "task_" + str(task_id)

        new_function_call["id"] = id_
        new_function_call["running"] = False
        new_function_call["completed"] = False
        new_function_call["type"] = 2
        new_function_call["stepsize"] = 0.0

        result = new_function_call["func"].split(".")
        new_function_call["model"] = self._model_engine.models[result[0]]
        new_function_call["func"] = getattr(self._model_engine.models[result[0]], result[1])

        self._tasks[id_] = new_function_call

    def add_task(self, new_task):
        task_id = int(random.random() * 10000)
        id_ = "task_" + str(task_id)
        new_task["id"] = id_
        new_task["running"] = False
        new_task["completed"] = False

        new_task["model"] = self._model_engine.models[new_task["model"]]

        current_value = getattr(new_task["model"], new_task["prop1"])
        if new_task["prop2"] is not None:
            if isinstance(current_value, dict):
                current_value = current_value[new_task["prop2"]]
            else:
                current_value = getattr(current_value, new_task["prop2"])
        new_task["current_value"] = current_value

        if isinstance(current_value, (int, float)) and not isinstance(current_value, bool):
            new_task["type"] = 0
        elif isinstance(current_value, (bool, str)):
            new_task["type"] = 1

        if new_task["it"] > 0:
            stepsize = (new_task["t"] - current_value) / (new_task["it"] / self._task_interval)
            new_task["stepsize"] = stepsize
            if stepsize != 0.0:
                self._tasks[id_] = new_task
        else:
            new_task["type"] = 1
            new_task["stepsize"] = 0.0
            self._tasks[id_] = new_task

        if new_task["type"] > 0:
            new_task["stepsize"] = 0.0
            self._tasks[id_] = new_task

    def remove_task(self, task_id):
        id_ = "task_" + str(task_id)
        if id_ in self._tasks:
            del self._tasks[id_]
            return True
        return False

    def remove_all_tasks(self):
        self._tasks = {}

    def run_tasks(self):
        if self._task_interval_counter > self._task_interval:
            self._task_interval_counter = 0.0

            for id_ in list(self._tasks.keys()):
                task = self._tasks[id_]
                remove_task = False

                if task["at"] < self._task_interval and not task["running"]:
                    task["at"] = 0

                    if task["type"] == 0:
                        task["running"] = True
                    elif task["type"] == 1:
                        task["current_value"] = task["t"]
                        self._set_value(task)
                        task["completed"] = True
                        remove_task = True
                    elif task["type"] == 2:
                        task["func"](*task["args"])
                        task["completed"] = True
                        remove_task = True
                else:
                    task["at"] -= self._task_interval

                if task["type"] < 1 and task["running"]:
                    if abs(task["current_value"] - task["t"]) < abs(task["stepsize"]):
                        task["current_value"] = task["t"]
                        self._set_value(task)
                        task["stepsize"] = 0
                        task["completed"] = True
                        remove_task = True
                    else:
                        task["current_value"] += task["stepsize"]
                        self._set_value(task)

                if remove_task and id_ in self._tasks:
                    del self._tasks[id_]

        if self.is_enabled:
            self._task_interval_counter += self._t

    def _set_value(self, task):
        if task["prop2"] is None:
            setattr(task["model"], task["prop1"], task["current_value"])
        else:
            target = getattr(task["model"], task["prop1"])
            if isinstance(target, dict):
                target[task["prop2"]] = task["current_value"]
            else:
                setattr(target, task["prop2"], task["current_value"])
