from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
import numpy as np

def case_079_circuit():
    qc = QuantumCircuit(3, 3)
    qc.h(0)
    qc.cp(np.pi / 2, 1, 0)
    qc.cp(np.pi / 4, 2, 0)
    qc.h(1)
    qc.cp(np.pi / 2, 2, 1)
    qc.h(2)
    qc.swap(0, 2)
    qc.iden(1)
    qc.measure([0, 1, 2], [0, 1, 2])
    backend = Aer.get_backend('local_qasm_simulator')
    job = backend.run(qc, shots=2048)
    return job.result().get_counts(qc)

if __name__ == '__main__':
    print(case_079_circuit())
