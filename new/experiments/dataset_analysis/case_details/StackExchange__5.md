# Case `StackExchange/5`

- **Split**: test
- **Group**: StackExchange
- **Buggy lines**: 16  |  **Fixed lines**: 16
- **Lines changed** (del/add/mod): 1 / 0 / 5
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.8889

## QChecker static analysis

2 finding(s); rules fired: `QC04`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *
from qiskit.providers.aer import QasmSimulator
simulator = QasmSimulator()
q = QuantumRegister(2)
c = ClassicalRegister(2)
qc = QuantumCircuit(q, c)
qc.h(q[0])
qc.cx(q[0], q[1])
qc.measure(q,c)
job_sim = execute(qc, backend=simulator, shots=1024)
counts_sim = job_sim.result().get_counts(qc)
qc.cx(q[0], q[1])
qc.measure(q,c)
job_sim2 = execute(qc, backend=simulator, shots=1024)
counts_sim2 = job_sim2.result().get_counts(qc)
qc.draw()
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit.providers.aer import QasmSimulator
q = QuantumRegister(2)
c1 = ClassicalRegister(2)
c2 = ClassicalRegister(2)
qc = QuantumCircuit(q, c1,c2)
qc.h(q[0])
qc.cx(q[0], q[1])
qc.measure(q,c1)
job_sim = execute(qc, backend=simulator, shots=1024)
counts_sim = job_sim.result().get_counts(qc)
qc.cx(q[0], q[1])
qc.measure(q,c2)
job_sim2 = execute(qc, backend=simulator, shots=1024)
counts_sim2 = job_sim2.result().get_counts(qc)
qc.draw()
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,15 +1,15 @@
 from qiskit import *
 from qiskit.providers.aer import QasmSimulator
-simulator = QasmSimulator()
 q = QuantumRegister(2)
-c = ClassicalRegister(2)
-qc = QuantumCircuit(q, c)
+c1 = ClassicalRegister(2)
+c2 = ClassicalRegister(2)
+qc = QuantumCircuit(q, c1,c2)
 qc.h(q[0])
 qc.cx(q[0], q[1])
-qc.measure(q,c)
+qc.measure(q,c1)
 job_sim = execute(qc, backend=simulator, shots=1024)
 counts_sim = job_sim.result().get_counts(qc)
 qc.cx(q[0], q[1])
-qc.measure(q,c)
+qc.measure(q,c2)
 job_sim2 = execute(qc, backend=simulator, shots=1024)
 counts_sim2 = job_sim2.result().get_counts(qc)
```
