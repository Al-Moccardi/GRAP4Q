# Case `Aer/bug_1`

- **Split**: train
- **Group**: Aer
- **Buggy lines**: 18  |  **Fixed lines**: 17
- **Lines changed** (del/add/mod): 1 / 0 / 0
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.9545

## QChecker static analysis

1 finding(s); rules fired: `QC04`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *

qr = QuantumRegister(5,'qr')
cr = ClassicalRegister(5, 'cr')
ghz = QuantumCircuit(qr, cr)

ghz.h(qr[0])
ghz.cx(qr[0],qr[1])
ghz.cx(qr[1],qr[2])
ghz.cx(qr[2],qr[3])
ghz.cx(qr[3],qr[4])
ghz.barrier(qr)
ghz.measure(qr,cr)
ghz.draw()

sim_backend = BasicAer.get_backend('statevector_simulator')
sim_result = execute(ghz, sim_backend).result()
print(sim_result.get_statevector(0))
```

## Fixed source (human gold)

```python
from qiskit import *

qr = QuantumRegister(5,'qr')
cr = ClassicalRegister(5, 'cr')
ghz = QuantumCircuit(qr, cr)

ghz.h(qr[0])
ghz.cx(qr[0],qr[1])
ghz.cx(qr[1],qr[2])
ghz.cx(qr[2],qr[3])
ghz.cx(qr[3],qr[4])
ghz.barrier(qr)
ghz.draw()

sim_backend = BasicAer.get_backend('statevector_simulator')
sim_result = execute(ghz, sim_backend).result()
print(sim_result.get_statevector(0))
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -11,5 +11,4 @@
 ghz.cx(qr[3],qr[4])
 ghz.barrier(qr)
-ghz.measure(qr,cr)
 ghz.draw()
```
