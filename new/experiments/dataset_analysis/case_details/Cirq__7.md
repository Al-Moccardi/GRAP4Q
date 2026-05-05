# Case `Cirq/7`

- **Split**: train
- **Group**: Cirq
- **Buggy lines**: 27  |  **Fixed lines**: 27
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
import numpy as np
import cirq 
class CustomGate(cirq.Gate):
    def __init__(self, unitary):
        self.unitary = unitary
        self.numQubits = int(np.log2(unitary.shape[0]))

    def _num_qubits_(self):
        return self.numQubits

    def _unitary_(self):
        return self.unitary

    def _circuit_diagram_info_(self, args='cirq.CircuitDiagramInfoArgs') -> 'cirq.CircuitDiagramInfo':
        return cirq.CircuitDiagramInfo(wire_symbols=("CG"), exponent=1.0, connected=True)

# Define custom gate
customUnitary = np.eye(4)    # The custom unitary matrix would go here
CG = CustomGate(customUnitary)

# Setup circuit
q = cirq.LineQubit.range(2)
circuit=cirq.Circuit()
circuit.append(CG(q[0], q[1]))

# Visualize circuit
print(circuit)
```

## Fixed source (human gold)

```python
import numpy as np
import cirq 
class CustomGate(cirq.Gate):
    def __init__(self, unitary):
        self.unitary = unitary
        self.numQubits = int(np.log2(unitary.shape[0]))

    def _num_qubits_(self):
        return self.numQubits

    def _unitary_(self):
        return self.unitary

    def _circuit_diagram_info_(self, args='cirq.CircuitDiagramInfoArgs') -> 'cirq.CircuitDiagramInfo':
        return cirq.CircuitDiagramInfo(wire_symbols=("CG","#2"), exponent=1.0, connected=True)

# Define custom gate
customUnitary = np.eye(4)    # The custom unitary matrix would go here
CG = CustomGate(customUnitary)

# Setup circuit
q = cirq.LineQubit.range(2)
circuit=cirq.Circuit()
circuit.append(CG(q[0], q[1]))

# Visualize circuit
print(circuit)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -13,5 +13,5 @@
 
     def _circuit_diagram_info_(self, args='cirq.CircuitDiagramInfoArgs') -> 'cirq.CircuitDiagramInfo':
-        return cirq.CircuitDiagramInfo(wire_symbols=("CG"), exponent=1.0, connected=True)
+        return cirq.CircuitDiagramInfo(wire_symbols=("CG","#2"), exponent=1.0, connected=True)
 
 # Define custom gate
```
