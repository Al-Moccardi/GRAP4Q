from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
import numpy as np

def case_076_circuit(theta=0.317, phi=0.515):
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.rx(theta, 0)
    qc.ry(phi, 1)
    qc.cx(0, 1)
    qc.rz(np.pi / 4, 1)
    qc.cx(0, 1)
    qc.id(0)
    qc.measure([0, 1], [0, 1])
    backend = Aer.get_backend('qasm_simulator')
    job = execute(qc, backend=backend, shots=2048)
    return job.result().get_counts(qc)

if __name__ == '__main__':
    print(case_076_circuit())
