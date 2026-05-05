# Case `StackExchange/6`

- **Split**: train
- **Group**: StackExchange
- **Buggy lines**: 23  |  **Fixed lines**: 23
- **Lines changed** (del/add/mod): 0 / 2 / 11
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.561

## QChecker static analysis

1 finding(s); rules fired: `QC02`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit
from qiskit import Aer, compile
from qiskit.backends.jobstatus import JOB_FINAL_STATES

n_qubits = 5
qc_list = []
for i in range(n_qubits):
    qr = QuantumRegister(n_qubits)
    cr = ClassicalRegister(n_qubits)
    qc = QuantumCircuit(qr, cr)
    qc.x(qr[i])
    qc.measure(qr, cr)
    qc_list.append(qc)

backend = Aer.get_backend('qasm_simulator')
qobj_list = [compile(qc, backend) for qc in qc_list]
job_list = [backend.run(qobj) for qobj in qobj_list]

while job_list:
    for job in job_list:
        if job.status() in JOB_FINAL_STATES:
            job_list.remove(job)
            print(job.result().get_counts())
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit
from qiskit import Aer

from qiskit.compiler import transpile, assemble

n_qubits = 5
qc_list = []

for i in range(n_qubits):
    qr = QuantumRegister(n_qubits)
    cr = ClassicalRegister(n_qubits)
    qc = QuantumCircuit(qr, cr)
    qc.x(qr[i])
    qc.measure(qr, cr)
    qc_list.append(qc)

backend = Aer.get_backend('qasm_simulator')
transpiled_circs = transpile(qc_list, backend=backend)
qobjs = assemble(transpiled_circs, backend=backend)
job_info = backend.run(qobjs)
for circ_index in range(len(transpiled_circs)):
    print(job_info.result().get_counts(transpiled_circs[circ_index]))
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,8 +1,11 @@
+from qiskit import *
 from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit
-from qiskit import Aer, compile
-from qiskit.backends.jobstatus import JOB_FINAL_STATES
+from qiskit import Aer
+
+from qiskit.compiler import transpile, assemble
 
 n_qubits = 5
 qc_list = []
+
 for i in range(n_qubits):
     qr = QuantumRegister(n_qubits)
@@ -14,10 +17,7 @@
 
 backend = Aer.get_backend('qasm_simulator')
-qobj_list = [compile(qc, backend) for qc in qc_list]
-job_list = [backend.run(qobj) for qobj in qobj_list]
-
-while job_list:
-    for job in job_list:
-        if job.status() in JOB_FINAL_STATES:
-            job_list.remove(job)
-            print(job.result().get_counts())
+transpiled_circs = transpile(qc_list, backend=backend)
+qobjs = assemble(transpiled_circs, backend=backend)
+job_info = backend.run(qobjs)
+for circ_index in range(len(transpiled_circs)):
+    print(job_info.result().get_counts(transpiled_circs[circ_index]))
```
