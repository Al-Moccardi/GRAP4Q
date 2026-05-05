# Case `StackExchange_2/bug_2`

- **Split**: test
- **Group**: StackExchange_2
- **Buggy lines**: 10  |  **Fixed lines**: 10
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 1.0

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *
from qiskit.visualization import *
from qiskit.quantum_info import *

sv = Statevector.from_label('01')
mycircuit = QuantumCircuit(2)
mycircuit.h(0)
mycircuit.cx(0,1)
new_sv = sv.evolve(mycircuit)
plot_state_qsphere(new_sv.data)
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit.visualization import *
from qiskit.quantum_info import *

sv = Statevector.from_label('10')
mycircuit = QuantumCircuit(2)
mycircuit.h(0)
mycircuit.cx(0,1)
new_sv = sv.evolve(mycircuit)
plot_state_qsphere(new_sv.data)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -3,5 +3,5 @@
 from qiskit.quantum_info import *
 
-sv = Statevector.from_label('01')
+sv = Statevector.from_label('10')
 mycircuit = QuantumCircuit(2)
 mycircuit.h(0)
```
