
from datetime import datetime
import sqlite3
import threading
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

DB_PATH = "tasks.db"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"   # ex: 27/10/2025 16:30
DATE_FORMAT = "%d/%m/%Y"
TIME_FORMAT = "%H:%M"

def get_conn():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            data TEXT NOT NULL,            -- dd/mm/yyyy
            horario TEXT NOT NULL,         -- HH:MM
            status TEXT,
            concluida INTEGER DEFAULT 0,
            scheduled_completion TEXT      -- datetime string no formato DATETIME_FORMAT (opcional)
        );
    """)
    conn.commit()
    conn.close()

# APScheduler (background)

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_mark_concluded(task_id: int, when: datetime):
    """
    Agenda um job que marcará a tarefa como concluída no datetime `when`.
    Criamos um job que abre sua própria conexão ao sqlite quando executa.
    """
    def job_action(tid):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE tarefas SET concluida = 1 WHERE id = ?", (tid,))
        conn.commit()
        conn.close()
        print(f"\n[agendador] Tarefa {tid} marcada como CONCLUÍDA ({datetime.now().strftime(DATETIME_FORMAT)})")

    trigger = DateTrigger(run_date=when)
    scheduler.add_job(job_action, trigger=trigger, args=[task_id], id=f"complete_{task_id}_{when.timestamp()}")

# Validações

def validar_data_hora(data_str: str, horario_str: str) -> bool:
    try:
        datetime.strptime(data_str, DATE_FORMAT)
        datetime.strptime(horario_str, TIME_FORMAT)
        return True
    except ValueError:
        return False

def parse_datetime_str(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, DATETIME_FORMAT)

# CRUD e lógica de negócio

def adicionar_tarefa_interativa():
    conn = get_conn()
    cur = conn.cursor()

    print("\n-- Cadastrar Tarefa --")
    titulo = input("Título da Tarefa: ").strip()
    data = input("Data: ").strip()
    horario = input("Horário: ").strip()

    if not validar_data_hora(data, horario):
        print("Formato inválido. Use dd/mm/aaaa e HH:MM. Registro cancelado.")
        conn.close()
        return

    # checar disponibilidade
    cur.execute("SELECT 1 FROM tarefas WHERE data = ? AND horario = ? AND concluida = 0", (data, horario))
    if cur.fetchone():
        print(f"Já existe uma tarefa agendada para {data} às {horario}. Escolha outro horário.")
        conn.close()
        return

    status = input("Status (ex: Leve / Urgente): ").strip()

    # opcional: data/hora para conclusão automática
    auto_complete = input("Agendar conclusão automática? (dd/mm/aaaa HH:MM) ou ENTER para pular: ").strip()
    scheduled_completion = None
    if auto_complete:
        try:
            when = parse_datetime_str(auto_complete)
            scheduled_completion = when.strftime(DATETIME_FORMAT)
        except ValueError:
            print("Formato de data/hora para conclusão inválido. Ignorando agendamento automático.")

    cur.execute(
        "INSERT INTO tarefas (titulo, data, horario, status, scheduled_completion) VALUES (?, ?, ?, ?, ?)",
        (titulo, data, horario, status, scheduled_completion)
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()

    print(f"Tarefa adicionada com sucesso! ID = {task_id}")

    # se agendamento fornecido, agenda o job
    if scheduled_completion:
        when = parse_datetime_str(scheduled_completion)
        # se a data já passou, não agendamos e marcamos imediatamente
        if when <= datetime.now():
            marcar_concluida(task_id)
            print("A data/hora de conclusão estava no passado — tarefa marcada como concluída agora.")
        else:
            schedule_mark_concluded(task_id, when)
            print(f"Conclusão automática agendada para {scheduled_completion}.")

def listar_tarefas():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tarefas ORDER BY data, horario")
    rows = cur.fetchall()
    conn.close()

    print("\n** Lista de Tarefas **")
    if not rows:
        print("Nenhuma tarefa cadastrada.")
        return

    header = f"{'ID':<4} {'Tarefa'.ljust(25)} | {'Data':<10} | {'Hora':<5} | {'Status'.ljust(10)} | {'Andamento':<10} | {'Agend. conclusão'}"
    print(header)
    print("-" * len(header))
    for r in rows:
        estado = "Concluída" if r["concluida"] else "Pendente"
        print(f"{r['id']:<4} {r['titulo'].ljust(25)} | {r['data']:<10} | {r['horario']:<5} | {str(r['status']).ljust(10)} | {estado:<10} | {r['scheduled_completion'] or '-'}")

    print("\nOpções:")
    print("1 - Excluir tarefa")
    print("2 - Marcar tarefa como concluída")
    print("0 - Voltar")
    try:
        opc = int(input("Escolha uma opção: ").strip())
    except ValueError:
        print("Opção inválida.")
        return

    if opc == 1:
        excluir_tarefa_interativa()
    elif opc == 2:
        try:
            tid = int(input("Digite o ID da tarefa a marcar como concluída: ").strip())
            marcar_concluida(tid)
        except ValueError:
            print("ID inválido.")
    elif opc == 0:
        return
    else:
        print("Opção inválida.")

def excluir_tarefa_interativa():
    try:
        tid = int(input("Digite o ID da tarefa a excluir: ").strip())
    except ValueError:
        print("ID inválido.")
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM tarefas WHERE id = ?", (tid,))
    if cur.rowcount:
        print("Tarefa excluída com sucesso.")
    else:
        print("Tarefa não encontrada.")
    conn.commit()
    conn.close()

def marcar_concluida(task_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE tarefas SET concluida = 1 WHERE id = ?", (task_id,))
    if cur.rowcount:
        print(f"Tarefa {task_id} marcada como concluída.")
    else:
        print("Tarefa não encontrada.")
    conn.commit()
    conn.close()

# Ao iniciar, re-agendamos jobs pendentes (caso o script reinicie)

def re_schedule_pending_jobs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, scheduled_completion FROM tarefas WHERE scheduled_completion IS NOT NULL AND concluida = 0")
    rows = cur.fetchall()
    conn.close()
    now = datetime.now()
    for r in rows:
        try:
            when = parse_datetime_str(r["scheduled_completion"])
            if when <= now:
                marcar_concluida(r["id"])
            else:
                schedule_mark_concluded(r["id"], when)
        except Exception:
            pass

# Menu principal

def menu_principal():
    init_db()
    re_schedule_pending_jobs()
    while True:
        print("\n= Organizador de Tarefas =")
        print("1 - Adicionar Tarefa")
        print("2 - Visualizar Tarefas")
        print("3 - Sair")
        try:
            op = int(input("Escolha uma opção: ").strip())
        except ValueError:
            print("Digite um número válido.")
            continue

        if op == 1:
            adicionar_tarefa_interativa()
        elif op == 2:
            listar_tarefas()
        elif op == 3:
            print("Finalizando...")
            scheduler.shutdown(wait=False)
            break
        else:
            print("Opção inválida.")

# Execução

if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário. Encerrando...")
        scheduler.shutdown(wait=False)
        sys.exit(0)
