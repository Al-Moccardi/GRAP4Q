"""Linear cluster state on a 4-qubit register.

Builds a 1D cluster state by Hadamarding all qubits then applying a
chain of CZ gates between neighbouring qubits. Includes identity
"wait" gates at the end.
"""
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


def build_cluster() -> QuantumCircuit:
    n = 4
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    for k in range(n):
        qc.h(qr[k])

    # Off-by-one: should be range(n-1) for qubits (k, k+1).
    for k in range(n):
        qc.cz(qr[k], qr[k + 1])

    for k in range(n):
        qc.iden(qr[k])

    qc.measure(qr, cr)
    return qc


def run_cluster():
    qc = build_cluster()
    backend = Aer.get_backend("qasm_simulator")
    job = execute(qc, backend=backend, shots=1024)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_cluster())
