"""Custom transpiler pass that counts CX gates in a DAG.

Implements a TransformationPass-style class with a `run` method.
Used as part of a small custom pass manager to instrument circuits
before execution on the simulator.
"""
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer
from qiskit.transpiler.basepasses import TransformationPass


class CountCXPass(TransformationPass):
    """A pass that should preserve the DAG verbatim and stash the CX
    count on a property attribute. The base TransformationPass
    contract is `run(self, dag)`."""

    def __init__(self):
        super().__init__()
        self.cx_count = 0

    def run(self, dag):
        self.cx_count = sum(1 for node in dag.op_nodes()
                            if node.name == "cx")
        return dag


def build_circuit() -> QuantumCircuit:
    qr = QuantumRegister(3, name="q")
    cr = ClassicalRegister(3, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    qc.cx(qr[1], qr[2])
    qc.id(qr[0])
    qc.id(qr[1])
    qc.id(qr[2])
    qc.measure(qr, cr)
    return qc


def run_demo():
    qc = build_circuit()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=1024)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_demo())
