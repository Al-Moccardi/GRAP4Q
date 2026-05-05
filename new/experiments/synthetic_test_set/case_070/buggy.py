from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
import numpy as np

def case_070_circuit(theta=0.471, phi=1.198):
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.rx(theta, 0)
    qc.ry(phi, 1)
    qc.cx(0, 1)
    qc.rz(np.pi / 4, 1)
    qc.cx(0, 1)
    qc.iden(0)
    qc.measure([0, 1], [0, 1])
    backend = Aer.get_backend('local_qasm_simulator')
    job = backend.run(qc, shots=2048)
    return job.result().get_data(qc)

if __name__ == '__main__':
    print(case_070_circuit())
