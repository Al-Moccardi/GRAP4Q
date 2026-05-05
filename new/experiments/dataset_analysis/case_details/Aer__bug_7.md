# Case `Aer/bug_7`

- **Split**: train
- **Group**: Aer
- **Buggy lines**: 11  |  **Fixed lines**: 12
- **Lines changed** (del/add/mod): 0 / 1 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 1.0

## QChecker static analysis

3 finding(s); rules fired: `QC02,QC03,QC04`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *
from qiskit.providers.aer import *
n = 3
q = QuantumRegister(n)
c = ClassicalRegister(n)
qc = QuantumCircuit(q, c, name="circuit")
qc.x(0)
qc.measure([1, 0, 2], [1, 0, 2])
BACKEND_OPTS_SV = {"method": "statevector"}
res_SV = execute([qc], QasmSimulator(), backend_options=BACKEND_OPTS_SV, shots=1).result()
print("counts = " + str(res_SV.get_counts()))
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit.providers.aer import *

n = 3
q = QuantumRegister(n)
c = ClassicalRegister(n)
qc = QuantumCircuit(q, c, name="circuit")
qc.x(0)
qc.measure([1, 0, 2], [0, 1, 2])
BACKEND_OPTS_SV = {"method": "statevector"}
res_SV = execute([qc], QasmSimulator(), backend_options=BACKEND_OPTS_SV, shots=1).result()
print("counts = " + str(res_SV.get_counts()))
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,4 +1,5 @@
 from qiskit import *
 from qiskit.providers.aer import *
+
 n = 3
 q = QuantumRegister(n)
@@ -6,5 +7,5 @@
 qc = QuantumCircuit(q, c, name="circuit")
 qc.x(0)
-qc.measure([1, 0, 2], [1, 0, 2])
+qc.measure([1, 0, 2], [0, 1, 2])
 BACKEND_OPTS_SV = {"method": "statevector"}
 res_SV = execute([qc], QasmSimulator(), backend_options=BACKEND_OPTS_SV, shots=1).result()
```
