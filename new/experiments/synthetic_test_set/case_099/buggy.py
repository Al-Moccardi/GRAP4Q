from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer

def case_099_circuit():
    qc = QuantumCircuit(3, 3)
    qc.h(1)
    qc.cx(1, 2)
    qc.cx(0, 1)
    qc.h(0)
    qc.iden(2)
    qc.measure([0, 1, 2], [0, 1, 2])
    backend = Aer.get_backend('qasm_simulator')
    job = backend.run(qc, shots=1024)
    return job.result().get_data(qc)

if __name__ == '__main__':
    print(case_099_circuit())
