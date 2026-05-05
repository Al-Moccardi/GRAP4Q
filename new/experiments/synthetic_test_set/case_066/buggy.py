from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer

def case_066_circuit():
    qc = QuantumCircuit(3, 3)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.id(0)
    qc.measure([0, 1, 2], [0, 1, 2])
    backend = Aer.get_backend('local_qasm_simulator')
    job = backend.run(qc, shots=2048)
    return job.result().get_data(qc)

if __name__ == '__main__':
    print(case_066_circuit())
