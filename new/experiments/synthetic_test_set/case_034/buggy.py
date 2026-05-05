from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer

def case_034_circuit():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.h(1)
    qc.cz(0, 1)
    qc.h(0)
    qc.h(1)
    qc.x(0)
    qc.x(1)
    qc.cz(0, 1)
    qc.x(0)
    qc.x(1)
    qc.h(0)
    qc.h(1)
    qc.iden(1)
    qc.measure([0, 1], [0, 1])
    backend = Aer.get_backend('qasm_simulator')
    job = backend.run(qc, shots=4096)
    return job.result().get_data(qc)

if __name__ == '__main__':
    print(case_034_circuit())
