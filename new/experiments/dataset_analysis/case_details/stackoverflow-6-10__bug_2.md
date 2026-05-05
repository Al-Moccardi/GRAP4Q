# Case `stackoverflow-6-10/bug_2`

- **Split**: train
- **Group**: stackoverflow-6-10
- **Buggy lines**: 16  |  **Fixed lines**: 16
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.9524

## QChecker static analysis

1 finding(s); rules fired: `QC02`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *
from qiskit.providers.aer import QasmSimulator

circuit = QuantumCircuit(2)
circuit.h(0)
circuit.h(1)
circuit.cx(0,1)
circuit.measure_all()

backend=QasmSimulator()
job_sim=backend.run(transpile(circuit,backend),shots=1024)
result_sim=job_sim.result()

counts=result_sim.get_counts(circuit)
print(counts)
print(circuit)
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit.providers.aer import QasmSimulator

circuit = QuantumCircuit(2)
circuit.h(0)
circuit.x(1)
circuit.cx(0,1)
circuit.measure_all()

backend=QasmSimulator()
job_sim=backend.run(transpile(circuit,backend),shots=1024)
result_sim=job_sim.result()

counts=result_sim.get_counts(circuit)
print(counts)
print(circuit)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -4,5 +4,5 @@
 circuit = QuantumCircuit(2)
 circuit.h(0)
-circuit.h(1)
+circuit.x(1)
 circuit.cx(0,1)
 circuit.measure_all()
```
