# Case `StackExchange/10`

- **Split**: test
- **Group**: StackExchange
- **Buggy lines**: 30  |  **Fixed lines**: 32
- **Lines changed** (del/add/mod): 0 / 1 / 9
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.7838

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.2222** (P=1.0, R=0.125)
- Edits produced: 2
- Rules fired: `R1,R7`

## Buggy source

```python
import qiskit as q
from qiskit.visualization import plot_histogram

circuit = q.QuantumCircuit(3, 3)

# entangle cubit 1 & 2

circuit.h(1)

circuit.cx(1, 2)

# apply CNOT to qubit we want to send
circuit.cx(0, 1)

circuit.h(0)

circuit.measure([0,1], [0,1])

circuit.cx(1, 2)

circuit.cz(0, 2)

print(circuit)

backend = q.Aer.get_backend('qasm_simulator')
job = q.execute(circuit, backend, shots=1024)
result = job.result()

counts = result.get_counts(circuit)
plot_histogram(counts)
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit.visualization import plot_histogram
q = QuantumRegister(3)
c = ClassicalRegister(3)
circuit = QuantumCircuit(q, c)

# entangle cubit 1 & 2

circuit.h(1)

circuit.cx(1, 2)

# apply CNOT to qubit we want to send
circuit.cx(0, 1)

circuit.h(0)

circuit.measure([0,1], [0,1])

circuit.z(q[2]).c_if(c[0],1)

circuit.x(q[2]).c_if(c[1],1)

qc.measure([2], [2])

backend = Aer.get_backend('qasm_simulator')
job = execute(circuit, backend, shots=1024)
result = job.result()

counts = result.get_counts(circuit)
print(counts)
plot_histogram(counts)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,6 +1,7 @@
-import qiskit as q
+from qiskit import *
 from qiskit.visualization import plot_histogram
-
-circuit = q.QuantumCircuit(3, 3)
+q = QuantumRegister(3)
+c = ClassicalRegister(3)
+circuit = QuantumCircuit(q, c)
 
 # entangle cubit 1 & 2
@@ -17,14 +18,15 @@
 circuit.measure([0,1], [0,1])
 
-circuit.cx(1, 2)
+circuit.z(q[2]).c_if(c[0],1)
 
-circuit.cz(0, 2)
+circuit.x(q[2]).c_if(c[1],1)
 
-print(circuit)
+qc.measure([2], [2])
 
-backend = q.Aer.get_backend('qasm_simulator')
-job = q.execute(circuit, backend, shots=1024)
+backend = Aer.get_backend('qasm_simulator')
+job = execute(circuit, backend, shots=1024)
 result = job.result()
 
 counts = result.get_counts(circuit)
+print(counts)
 plot_histogram(counts)
```
