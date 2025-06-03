import threading
import time
from queue import Queue

# ====================== CLASSE DO PROCESSO ======================

class Processo:   #- Estruture os processos com campos: ID, tempo de chegada, tempo restante, quantum restante, estado (S)
    def __init__(self, id, chegada, exec1, bloqueio, espera, exec2):
        self.id = id
        self.chegada = chegada
        self.exec1 = exec1
        self.exec2 = exec2
        self.bloqueio = bloqueio
        self.espera = espera

        self.estado = 'novo'
        self.tempo_restante = exec1
        self.em_execucao2 = False
        self.tempo_bloqueado = 0
        self.tempo_espera = 0
        self.tempo_inicio = None
        self.tempo_fim = None
        self.quantum_restante = 0
        self.turnaround = 0
        self.contextos = 0

    def __repr__(self):
        return f"Processo({self.id})"

# ====================== FUNÇÃO PARA CARREGAR PROCESSOS ======================

def carregar_processos(caminho):       # A entrada será feita via arquivo texto (2)
    processos_iniciais = []
    processos_dinamicos = []
    with open(caminho, 'r') as f:
        for linha in f:
            if linha.strip() == "":
                continue
            partes = linha.strip().split('|')
            id = partes[0].strip()                      # Identificador do processo
            chegada = int(partes[1].strip())            # Quando o processo entra no sistema
            exec1 = int(partes[2].strip())              # Quanto tempo o processo roda antes de possivelmente bloquear
            bloqueio = partes[3].strip().lower() == 's' # Se o processo faz E/S após Exec1 (S = Sim, N = Não)
            espera = int(partes[4].strip())             # Quanto tempo ele fica bloqueado antes de retornar para continuar
            exec2 = int(partes[5].strip())              # Tempo restante que ele ainda precisa rodar depois do desbloqueio

            proc = Processo(id, chegada, exec1, bloqueio, espera, exec2)
            if chegada == 0:
                processos_iniciais.append(proc)
            else:
                processos_dinamicos.append(proc)

    return processos_iniciais, processos_dinamicos

# ====================== ESCALONADOR ROUND ROBIN ======================

# - Round Robin com quantum fixo e dinâmico. (1)
class Escalonador:
    def __init__(self, num_nucleos, quantum, processos_iniciais, processos_dinamicos, quantum_dinamico=False):
        self.num_nucleos = num_nucleos
        self.quantum = quantum
        self.prontos = Queue()         #- Use filas para organizar processos (S) 
        self.bloqueados = []
        self.execucao = [None] * num_nucleos
        self.nucleos = []
        self.lock = threading.Lock()
        self.tempo = 0
        self.dinamicos = processos_dinamicos
        self.finalizados = []
        self.timeline = [[] for _ in range(num_nucleos)]
        self.quantum_dinamico = quantum_dinamico

        for p in processos_iniciais:
            self.prontos.put(p)

    # ====================== FUNÇÃO PARA CRIAR THREADS ======================

    def iniciar(self):
        for i in range(self.num_nucleos):
            t = threading.Thread(target=self.executar_nucleo, args=(i,))
            t.start()
            self.nucleos.append(t)

        threading.Thread(target=self.monitorar_dinamicos).start()
        threading.Thread(target=self.verificar_bloqueios).start()

    def atualizar_tempo(self, tempo):
        self.tempo = tempo

    def executar_nucleo(self, idx):
        while True:
            with self.lock:
                if self.prontos.empty() and all(p is None for p in self.execucao) and not self.bloqueados and not self.dinamicos:
                    break
                if not self.prontos.empty():
                    processo = self.prontos.get()
                    processo.contextos += 1
                    if processo.tempo_inicio is None:
                        processo.tempo_inicio = self.tempo
                    processo.estado = 'executando'
                    if self.quantum_dinamico:
                        processo.quantum_restante = min(self.quantum, processo.tempo_restante)                #Se o processo tem só 1 unidade restante, e o quantum é 3 → ele recebe 1
                    else:                                                                                     #Se o processo tem 2 restantes, e o quantum é 3 → recebe 2
                        processo.quantum_restante = self.quantum                                              #Isso evita desperdiçar quantum e melhora o uso da CPU
                    self.execucao[idx] = processo
                else:
                    self.timeline[idx].append(" ocioso ")
                    time.sleep(1)
                    continue

            while processo.quantum_restante > 0 and processo.tempo_restante > 0:       #- A cada passo do tempo, verifique desbloqueios, atualize execuções, aplique o RR (S)    
                time.sleep(1)
                processo.tempo_restante -= 1
                processo.quantum_restante -= 1
                self.timeline[idx].append(processo.id)

                if processo.tempo_restante == 0:
                    if processo.bloqueio and not processo.em_execucao2:   #- Processos que executam, bloqueiam para I/O e retornam à fila (1)
                        processo.estado = 'bloqueado'
                        processo.tempo_bloqueado = processo.espera
                        processo.tempo_restante = processo.exec2
                        processo.em_execucao2 = True
                        with self.lock:
                            self.bloqueados.append(processo)
                        break
                    else:
                        processo.estado = 'finalizado'
                        processo.tempo_fim = self.tempo + 1
                        processo.turnaround = processo.tempo_fim - processo.chegada
                        with self.lock:
                            self.finalizados.append(processo)
                        break

            if processo.estado == 'executando':  # Quantum acabou antes de terminar
                processo.estado = 'pronto'
                with self.lock:
                    self.prontos.put(processo)

            with self.lock:
                self.execucao[idx] = None

    def verificar_bloqueios(self):
        while True:
            time.sleep(1)
            with self.lock:
                for processo in self.bloqueados[:]:      #- A cada passo do tempo, verifique desbloqueios, atualize execuções, aplique o RR (S)
                    processo.tempo_bloqueado -= 1
                    if processo.tempo_bloqueado <= 0:
                        processo.estado = 'pronto'
                        self.bloqueados.remove(processo)
                        self.prontos.put(processo)
            if not self.bloqueados and self.prontos.empty() and all(p is None for p in self.execucao) and not self.dinamicos:
                break

    def monitorar_dinamicos(self):  #- Chegada dinâmica de processos durante a simulação (1)
        while self.dinamicos:
            with self.lock:
                for p in self.dinamicos[:]:
                    if p.chegada <= self.tempo:
                        self.prontos.put(p)
                        self.dinamicos.remove(p)
            time.sleep(1)

    def aguardar_fim(self):
        for t in self.nucleos:
            t.join()

    def finalizado(self):
        return not self.dinamicos and self.prontos.empty() and all(p is None for p in self.execucao) and not self.bloqueados

    def gerar_relatorio(self):  #- Tabela: tempo de espera, turnaround, número de trocas de contexto (3)
        with open('relatorio.txt', 'w', encoding='utf-8') as f:
            f.write("ID | Espera | Turnaround | Trocas de contexto\n")
            for p in sorted(self.finalizados, key=lambda x: x.id):
                espera = p.turnaround - (p.exec1 + (p.exec2 if p.bloqueio else 0) + (p.espera if p.bloqueio else 0))
                f.write(f"{p.id} | {espera} | {p.turnaround} | {p.contextos - 1}\n")

            f.write("\nLinha do tempo (Gantt):\n")        #- Linha do tempo textual estilo Gantt (3)
            for idx, linha in enumerate(self.timeline):
                f.write(f"Núcleo {idx}: {' | '.join(linha)}\n")

# ====================== MAIN.PY ======================

# - Round Robin com quantum fixo e dinamico. (1)
QUANTUM_BASE = 3
QUANTUM_DINAMICO = True  # True para ativar quantum dinâmico, False para fixo
NUM_NUCLEOS = 2  # - Execucao em multiplos nucleos (ex: 2 ou 4). (1)
ARQUIVO_ENTRADA = 'entrada.txt'
tempo_global = 0
tempo_lock = threading.Lock()

def atualizar_tempo():     #- O tempo será controlado por uma variável global (S)
    global tempo_global
    while not escalonador.finalizado():
        time.sleep(1)
        with tempo_lock:
            tempo_global += 1
        escalonador.atualizar_tempo(tempo_global)

if __name__ == "__main__":
    print("Iniciando simulação Round Robin com múltiplos núcleos...\n")

    processos_iniciais, processos_dinamicos = carregar_processos(ARQUIVO_ENTRADA)
    escalonador = Escalonador(NUM_NUCLEOS, QUANTUM_BASE, processos_iniciais, processos_dinamicos, QUANTUM_DINAMICO)

    tempo_thread = threading.Thread(target=atualizar_tempo)  #- Utilize threads para simular o tempo e a chegada dinâmica (S)
    tempo_thread.start()

    escalonador.iniciar()
    escalonador.aguardar_fim()
    tempo_thread.join()

    escalonador.gerar_relatorio()
    print("\nSimulação concluída. Relatório gerado em 'relatorio.txt'")
