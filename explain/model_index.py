"""Central registry of model classes.

Mirrors src/explain/ModelIndex.js. The loader looks up classes by `model_type`
strings from the JSON scenario files. Every new model class must be added here.

For the spike, only Capacitance and Resistor are registered — enough to prove
the architecture end-to-end on a two-compartment toy scenario.
"""

from .base_models.blood_diffusor import BloodDiffusor
from .base_models.capacitance import Capacitance
from .base_models.container import Container
from .base_models.gas_diffusor import GasDiffusor
from .base_models.gas_exchanger import GasExchanger
from .base_models.resistor import Resistor
from .base_models.time_varying_elastance import TimeVaryingElastance
from .component_models.ans import Ans
from .component_models.ans_afferent import AnsAfferent
from .component_models.ans_efferent import AnsEfferent
from .component_models.blood import Blood
from .component_models.blood_capacitance import BloodCapacitance
from .component_models.blood_pump import BloodPump
from .component_models.blood_time_varying_elastance import BloodTimeVaryingElastance
from .component_models.blood_vessel import BloodVessel
from .component_models.breathing import Breathing
from .component_models.circulation import Circulation
from .component_models.fluids import Fluids
from .component_models.gas import Gas
from .component_models.gas_capacitance import GasCapacitance
from .component_models.heart import Heart
from .component_models.heart_chamber import HeartChamber
from .component_models.heart_valve import HeartValve
from .component_models.metabolism import Metabolism
from .component_models.mob2 import Mob2
from .component_models.pda import Pda
from .component_models.placenta import Placenta
from .component_models.respiration import Respiration
from .component_models.shunts import Shunts
from .device_models.ecls import Ecls
from .device_models.monitor import Monitor
from .device_models.resuscitation import Resuscitation
from .device_models.ventilator import Ventilator

MODEL_INDEX = {
    # base models
    "BloodDiffusor": BloodDiffusor,
    "Capacitance": Capacitance,
    "Container": Container,
    "GasDiffusor": GasDiffusor,
    "GasExchanger": GasExchanger,
    "Resistor": Resistor,
    "TimeVaryingElastance": TimeVaryingElastance,
    # component models
    "Ans": Ans,
    "AnsAfferent": AnsAfferent,
    "AnsEfferent": AnsEfferent,
    "Blood": Blood,
    "BloodCapacitance": BloodCapacitance,
    "BloodPump": BloodPump,
    "BloodTimeVaryingElastance": BloodTimeVaryingElastance,
    "BloodVessel": BloodVessel,
    "Breathing": Breathing,
    "Circulation": Circulation,
    "Fluids": Fluids,
    "Gas": Gas,
    "GasCapacitance": GasCapacitance,
    "Heart": Heart,
    "HeartChamber": HeartChamber,
    "HeartValve": HeartValve,
    "Metabolism": Metabolism,
    "Mob2": Mob2,
    "Pda": Pda,
    "Placenta": Placenta,
    "Respiration": Respiration,
    "Shunts": Shunts,
    # device models
    "Ecls": Ecls,
    "Monitor": Monitor,
    "Resuscitation": Resuscitation,
    "Ventilator": Ventilator,
}
