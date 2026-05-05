# Case `Cirq/1`

- **Split**: val
- **Group**: Cirq
- **Buggy lines**: 18  |  **Fixed lines**: 18
- **Lines changed** (del/add/mod): 0 / 0 / 2
- **API drift**: 0.0  |  **Identifier Jaccard**: 1.0

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
import cirq
import pytest

@pytest.mark.parametrize('n', [1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_decomposition_unitary(n):
    rs = np.random.RandomState(1234)
    diagonal_angles = rs.rand(2 ** n)
    diagonal_gate = cirq.DiagonalGate(diagonal_angles)
    decomposed_circ = cirq.Circuit(cirq.decompose(diagonal_gate(*cirq.LineQubit.range(n))))

    expected_f = [np.exp(1j * angle * 2 * np.pi) for angle in diagonal_angles]
    assert cirq.is_unitary(np.diag(expected_f))
    assert cirq.is_diagonal(np.diag(expected_f))
    actual_unitary = cirq.unitary(decomposed_circ)
    cirq.testing.assert_allclose_up_to_global_phase(actual_unitary, np.diag(expected_f), rtol=1e-4, atol=1e-4)
    decomposed_f = actual_unitary.diagonal()

    np.testing.assert_allclose(decomposed_f, expected_f)
```

## Fixed source (human gold)

```python
import cirq
import pytest

@pytest.mark.parametrize('n', [1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_decomposition_unitary(n):
    rs = np.random.RandomState(1234)
    diagonal_angles = [2 * np.pi * angle for angle in rs.rand(2 ** n)]
    diagonal_gate = cirq.DiagonalGate(diagonal_angles)
    decomposed_circ = cirq.Circuit(cirq.decompose(diagonal_gate(*cirq.LineQubit.range(n))))

    expected_f = [np.exp(1j * angle) for angle in diagonal_angles]
    assert cirq.is_unitary(np.diag(expected_f))
    assert cirq.is_diagonal(np.diag(expected_f))
    actual_unitary = cirq.unitary(decomposed_circ)
    cirq.testing.assert_allclose_up_to_global_phase(actual_unitary, np.diag(expected_f), rtol=1e-4, atol=1e-4)
    decomposed_f = actual_unitary.diagonal()

    np.testing.assert_allclose(decomposed_f, expected_f)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -5,9 +5,9 @@
 def test_decomposition_unitary(n):
     rs = np.random.RandomState(1234)
-    diagonal_angles = rs.rand(2 ** n)
+    diagonal_angles = [2 * np.pi * angle for angle in rs.rand(2 ** n)]
     diagonal_gate = cirq.DiagonalGate(diagonal_angles)
     decomposed_circ = cirq.Circuit(cirq.decompose(diagonal_gate(*cirq.LineQubit.range(n))))
 
-    expected_f = [np.exp(1j * angle * 2 * np.pi) for angle in diagonal_angles]
+    expected_f = [np.exp(1j * angle) for angle in diagonal_angles]
     assert cirq.is_unitary(np.diag(expected_f))
     assert cirq.is_diagonal(np.diag(expected_f))
```
