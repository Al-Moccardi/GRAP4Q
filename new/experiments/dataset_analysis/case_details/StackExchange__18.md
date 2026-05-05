# Case `StackExchange/18`

- **Split**: train
- **Group**: StackExchange
- **Buggy lines**: 10  |  **Fixed lines**: 8
- **Lines changed** (del/add/mod): 0 / 0 / 8
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.1622

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
import qiskit as qt
from qiskit.aqua.circuits import FourierTransformCircuits as QFT

    circuit = qt.QuantumCircuit(3)
    circuit.initialize( psi, [i for i in reversed(circuit.qubits)])

    QFT.construct_circuit(circuit=circuit, qubits=circuit.qubits[:2], inverse=True)

    backend = qt.Aer.get_backend('statevector_simulator')
    final_state = qt.execute(circuit, backend, shots=1).result().get_statevector()
```

## Fixed source (human gold)

```python
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

iqft = QFT(3, inverse=True)  # get the IQFT
reversed_bits_QFT = iqft.reverse_bits()  # reverse bit order

circuit = QuantumCircuit(3)
circuit.compose(reversed_bits_QFT, inplace=True)  # append your QFT
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,10 +1,8 @@
-import qiskit as qt
-from qiskit.aqua.circuits import FourierTransformCircuits as QFT
+from qiskit import QuantumCircuit
+from qiskit.circuit.library import QFT
 
-    circuit = qt.QuantumCircuit(3)
-    circuit.initialize( psi, [i for i in reversed(circuit.qubits)])
+iqft = QFT(3, inverse=True)  # get the IQFT
+reversed_bits_QFT = iqft.reverse_bits()  # reverse bit order
 
-    QFT.construct_circuit(circuit=circuit, qubits=circuit.qubits[:2], inverse=True)
-
-    backend = qt.Aer.get_backend('statevector_simulator')
-    final_state = qt.execute(circuit, backend, shots=1).result().get_statevector()
+circuit = QuantumCircuit(3)
+circuit.compose(reversed_bits_QFT, inplace=True)  # append your QFT
```
