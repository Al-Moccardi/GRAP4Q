# Case `Aer/bug_10`

- **Split**: train
- **Group**: Aer
- **Buggy lines**: 48  |  **Fixed lines**: 48
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.9844

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 1
- Rules fired: `R6`

## Buggy source

```python
import qiskit
from qiskit import transpile, schedule as build_schedule
from qiskit.test.mock import FakeAlmaden
from qiskit import Aer, IBMQ, execute
from qiskit import QuantumCircuit
from qiskit.circuit import Gate

from qiskit import pulse
from qiskit.ignis.characterization.calibrations import rabi_schedules, RabiFitter

from qiskit.pulse import DriveChannel
from qiskit.compiler import assemble
from qiskit.qobj.utils import MeasLevel, MeasReturnType
# The pulse simulator
from qiskit.providers.aer import PulseSimulator

# Object for representing physical models
from qiskit.providers.aer.pulse import PulseSystemModel

# Mock Armonk backend
from qiskit.test.mock.backends.armonk.fake_armonk import FakeArmonk

# backend = qiskit.providers.aer.PulseSimulator()
backend = FakeAlmaden()
print(backend.configuration().hamiltonian)
# schedule = build_schedule(transpiled_circ, backend)
circ = QuantumCircuit(2, 2)
circ.x(0)
circ.x(0)
circ.x(1)
circ.measure([0, 1], [0, 1])

schedule = build_schedule(circ, backend,
                          method="as_late_as_possible")
# schedule.draw(channels=[pulse.DriveChannel(0), pulse.DriveChannel(1)])


backend_sim = PulseSimulator()

qobj = assemble(schedule,
                     backend=backend_sim,
                     meas_level=1,
                     meas_return='avg',
                     shots=1)
print('line 45')
fakealmaden_model = PulseSystemModel.from_backend(backend)
print('line47')
sim_result = backend_sim.run(qobj, fakealmaden_model).result()
```

## Fixed source (human gold)

```python
import qiskit
from qiskit import transpile, schedule as build_schedule
from qiskit.test.mock import FakeAlmaden
from qiskit import Aer, IBMQ, execute
from qiskit import QuantumCircuit
from qiskit.circuit import Gate

from qiskit import pulse
from qiskit.ignis.characterization.calibrations import rabi_schedules, RabiFitter

from qiskit.pulse import DriveChannel
from qiskit.compiler import assemble
from qiskit.qobj.utils import MeasLevel, MeasReturnType
# The pulse simulator
from qiskit.providers.aer import PulseSimulator

# Object for representing physical models
from qiskit.providers.aer.pulse import PulseSystemModel

# Mock Armonk backend
from qiskit.test.mock.backends.armonk.fake_armonk import FakeArmonk

# backend = qiskit.providers.aer.PulseSimulator()
backend = FakeAlmaden()
print(backend.configuration().hamiltonian)
# schedule = build_schedule(transpiled_circ, backend)
circ = QuantumCircuit(2, 2)
circ.x(0)
circ.x(0)
circ.x(1)
circ.measure([0, 1], [0, 1])

schedule = build_schedule(circ, backend,
                          method="as_late_as_possible")
# schedule.draw(channels=[pulse.DriveChannel(0), pulse.DriveChannel(1)])


backend_sim = PulseSimulator()

qobj = assemble(schedule,
                     backend=backend_sim,
                     meas_level=1,
                     meas_return='avg',
                     shots=1)
print('line 45')
fakealmaden_model = PulseSystemModel.from_backend(backend, subsystem_list=[0, 1])
print('line47')
sim_result = backend_sim.run(qobj, fakealmaden_model).result()
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -44,5 +44,5 @@
                      shots=1)
 print('line 45')
-fakealmaden_model = PulseSystemModel.from_backend(backend)
+fakealmaden_model = PulseSystemModel.from_backend(backend, subsystem_list=[0, 1])
 print('line47')
 sim_result = backend_sim.run(qobj, fakealmaden_model).result()
```
