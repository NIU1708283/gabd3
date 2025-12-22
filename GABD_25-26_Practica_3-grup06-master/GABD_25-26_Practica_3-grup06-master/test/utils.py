import array
from typing import Optional, List, Union, Dict
from ucimlrepo import fetch_ucirepo, list_available_datasets
import numpy as np
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from oracledb import LOB
import random
import io
from contextlib import redirect_stdout
import json

import socket
import nbformat
import re


import pytest
from pymongo import MongoClient



def check_esquema(db, table_structure : Dict[str, Dict]) -> Dict[str, Union[str, Dict]]:
    """
    Comprova si les taules i les seves columnes/restriccions de l'esquema actual
    coincideixen amb el contingut de `table_structure`.
    Retorna un informe amb coincidències i discrepàncies.
    """

    status = True
    cursor = db.cursor()
    report = {}

    for table_name, table_def in table_structure.items():
        table_report = {"missing_columns": [], "type_mismatch": [], "constraints_mismatch": [], "ok": []}

        # --- 1️⃣ Comprovar que la taula existeix ---
        cursor.execute("""
            SELECT COUNT(*) FROM user_tables WHERE table_name = :t
        """, {"t": table_name.upper()})
        exists = cursor.fetchone()[0]
        if not exists:
            report[table_name] = f"❌ La taula {table_name} no existeix."
            status = False
            continue

        # --- 2️⃣ Llistar columnes i tipus actuals ---
        cursor.execute("""
            SELECT column_name, data_type, data_length, data_precision, data_scale
            FROM user_tab_columns
            WHERE table_name = :t
        """, {"t": table_name.upper()})
        cols_db = {r[0]: r[1] for r in cursor.fetchall()}

        # --- 3️⃣ Comprovar columnes i tipus ---
        for col_name, col_def in table_def.get("columns", {}).items():
            expected_type = col_def["type"].upper()
            db_type = cols_db.get(col_name.upper())

            if db_type is None:
                table_report["missing_columns"].append(col_name)
                status = False
            elif not db_type.startswith(expected_type.split("(")[0]):  # tolerar mida diferent
                table_report["type_mismatch"].append((col_name, expected_type, db_type))
            else:
                table_report["ok"].append(col_name)

        # --- 4️⃣ Comprovar restriccions primàries i externes ---
        cursor.execute("""
            SELECT constraint_name, constraint_type
            FROM user_constraints
            WHERE table_name = :t
        """, {"t": table_name.upper()})
        constraints = cursor.fetchall()

        pk_cols = []
        fk_defs = []

        for cname, ctype in constraints:
            if ctype == 'P':  # Primary Key
                cursor.execute("""
                    SELECT column_name FROM user_cons_columns
                    WHERE constraint_name = :c
                    ORDER BY position
                """, {"c": cname})
                pk_cols = [r[0] for r in cursor.fetchall()]
            elif ctype == 'R':  # Foreign Key
                cursor.execute("""
                    SELECT a.column_name, c_pk.table_name, b.column_name, c.delete_rule
                    FROM user_cons_columns a
                    JOIN user_constraints c ON a.constraint_name = c.constraint_name
                    JOIN user_cons_columns b ON c.r_constraint_name = b.constraint_name
                    JOIN user_constraints c_pk ON b.constraint_name = c.r_constraint_name
                    WHERE a.constraint_name = :c
                """, {"c": cname})
                fk_defs += cursor.fetchall()

        # Comprovació de la PK
        expected_pk = [c.upper() for c in table_def.get("constraints", {}).get("primary_key", [])]
        if pk_cols and sorted(pk_cols) != sorted(expected_pk):
            table_report["constraints_mismatch"].append(
                ("PRIMARY KEY", expected_pk, pk_cols)
            )
            status = False

        # Comprovació de FK
        expected_fks = table_def.get("constraints", {}).get("foreign_keys", {})
        for fk_col, fk_info in expected_fks.items():
            found = False
            for col, ref_table, ref_col, delete_rule in fk_defs:
                if col == fk_col.upper() and ref_table == fk_info["ref_table"].upper():
                    found = True
                    break
            if not found:
                table_report["constraints_mismatch"].append(
                    (f"FOREIGN KEY {fk_col}", fk_info)
                )
                status = False

        report[table_name] = table_report

    cursor.close()
    return report , status


def free_space(client, disks: Optional[Union[List[str], str]] = '/', avail_space_threshold_gb: float = 1.0) -> dict:
    list_disk = " ".join(disks) if isinstance(disks, list) else disks
    stdin, stdout, stderr = client.exec_command('df -h ' + list_disk)
    output = stdout.read().decode()
    print("Disk Space Info:\n", output)
    # output dictionary composed of disk_path: avail_space
    free_disc = {}
    low_space_disks = {}
    # Parse the output to find available space
    for lines in output.splitlines():
        if len(lines) > 1:
            parts = lines.split()
            if len(parts) >= 4:
                disk = parts[0]
                avail_space = parts[3]
                print(f"Available space: {avail_space}")
                # Assuming the format is in GB for simplicity
                if avail_space.endswith('G'):
                    avail_gb = float(avail_space[:-1])
                    free_disc[disk] = avail_gb
                    if avail_gb < avail_space_threshold_gb:
                        low_space_disks[disk] = avail_gb
                elif avail_space.endswith('M'):
                    avail_gb = float(avail_space[:-1]) / 1024
                    free_disc[disk] = avail_gb
                    if avail_gb < avail_space_threshold_gb:
                        low_space_disks[disk] = avail_gb
                elif avail_space.endswith('K'):
                    avail_gb = float(avail_space[:-1]) / (1024 * 1024)
                    free_disc[disk] = avail_gb
                    if avail_gb < avail_space_threshold_gb:
                        low_space_disks[disk] = avail_gb


    # Llençar l'excepció si hi ha algun disk amb poc espai
    if low_space_disks:
        raise Exception("Some disks have less than 1GB free space!", "NO_DISK_SPACE", low_space_disks)

    return free_disc

def check_rol_user(db_conn, user, rol):
    """
       Retorna un llistat amb els rols que l'usuari te assignats directament i Cert o Fals si en aquesta llista apareix el rol: rol
       """

    with db_conn.cursor() as cursor:
        sql = f"""SELECT GRANTED_ROLE, DEFAULT_ROLE
               FROM DBA_ROLE_PRIVS
               WHERE GRANTEE = '{user.upper()}'"""
        rols = cursor.execute(sql).fetchall()

    # mirem si rol està a rols
    rols_user = [r[0] for r in rols]
    return rols_user, any(rol.lower() in r.lower() for r in rols_user)


def check_datasets(db_conn, nameDataset: Union[str, List]) -> dict:
    """
    Comprova que les dades dels datasets de la UCI s'han importat correctament a la base de dades.
    :param db_conn:
    :param nameDataset:
    :return:
    """
    report = {}
    status = True
    if isinstance(nameDataset, list):
        reports = {}
        status = True
        for name in nameDataset:
            reports[name], status_tmp = check_datasets(db_conn, name)
            status = status and status_tmp
        return reports, status

    dataset = fetch_ucirepo(name=nameDataset)


    # data (as pandas dataframes)
    df = dataset.data.features

    # Mirem el nombre de files que hi ha al dataframe
    num_samples = len(df)

    # Mirem que la dimensio de les features

    # Recuperar informació de la taula
    sql = f"""select count(*) from dataset d join samples s on d.id=s.id_dataset 
                                      where  d.name='{nameDataset}'
                                      order by s.id"""

    with db_conn.cursor() as cursor:
        cursor.execute(sql)
        num  = cursor.fetchall()[0][0]
        if num != num_samples:
            report['Numero de Mostres'] = f"Hi ha {num} mostres quan s'esperaven {num_samples}"
            status = False
        else:
            report['Numero de Mostres'] = f"Hi ha {num} mostres com s'esperaven."

    # Fem un mostreig random de 1% de mostres (arrondit a l'enter superior) i com a màxim 20
    sample_size = min(max(1, int(num_samples * 0.01)),20)
    sample_df = df.sample(n=sample_size, random_state=42)
    valors_correctes = 0.0
    for index, sample_row in sample_df.iterrows():
        sample_id = sample_row.name
        # print(sample_id)
        sql = f"""select features,label 
                from dataset d join samples s on d.id=s.id_dataset
                where d.name='{nameDataset}' and s.id={sample_id}"""
        with db_conn.cursor() as cursor:
            res = cursor.execute(sql)
            row = res.fetchone()
            if row is None:
                report['Mostres Correctes'] = f"0 de {sample_size} mostres correctes"
                report['Score'] = 0
                return report, False

            if isinstance(row[0], array.array):
                vec = np.array(row[0])
            if isinstance(row[0], LOB):
                vec = np.fromstring(row[0].read().strip('[]'), sep=',')
            valors_correctes += (max(abs(sample_row.to_numpy() - vec)) < 1.e-3)

    report['Mostres Correctes'] = f"{valors_correctes} correctes de {sample_size} mostres seleccionades aleatoriament"
    report['Score'] = (valors_correctes / sample_size)*status

    return report, status

def obtain_esquema(db_conn, schema : str ):
    """
    Recupera les taules, claus primàries i foranes d'un esquema de la base de dades. Genera un graf on els nodes son les taules i les arestes les claus foranies
    :param db_conn:
    :param schema:
    :return:
    """

    # Recuperar informació de les taules
    with db_conn.cursor() as cursor:
        sql = f"""
            SELECT table_name
            FROM all_tables
            WHERE owner = UPPER('{schema}')
            ORDER BY table_name
            """
        cursor.execute(sql)
        tables = [row[0] for row in cursor.fetchall()]

        fk_relations = []
        for table in tables:
            sql = f"""
            SELECT 
                acc.column_name,
                r.table_name AS foreign_table_name,
                rcc.column_name AS foreign_column_name
            FROM user_constraints uc
            JOIN user_cons_columns acc
                ON uc.constraint_name = acc.constraint_name
            JOIN user_constraints r
                ON uc.r_constraint_name = r.constraint_name
            JOIN user_cons_columns rcc
                ON r.constraint_name = rcc.constraint_name
                   AND acc.position = rcc.position
            WHERE uc.constraint_type = 'R'
              AND uc.table_name = '{table}'
            ORDER BY acc.position
            """
            cursor.execute(sql)
            for row in cursor.fetchall():
                fk_relations.append((table, row[0], row[1], row[2]))

    # Crear el graf amb networkx
    G = nx.DiGraph()
    G.add_nodes_from(tables)
    for table, column, foreign_table, foreign_column in fk_relations:
        G.add_edge(table, foreign_table, label=f"{column} -> {foreign_column}")

    # Per cada taula, afegir la informació de la clau primària com a atribut del node
    with db_conn.cursor() as cursor:
        for table in tables:
            sql = f"""
                SELECT acc.column_name
                FROM user_constraints uc
                JOIN user_cons_columns acc
                    ON uc.constraint_name = acc.constraint_name
                WHERE uc.constraint_type = 'P'
                  AND uc.table_name = '{table}'
                ORDER BY acc.position
                """
            cursor.execute(sql)
            pk_columns = [row[0] for row in cursor.fetchall()]
            G.nodes[table]['primary_key'] = pk_columns

    return G

def draw_esquema(G, output_file: str = "esquema.png"):
    """
    Dibuixa el graf de l'esquema i el desa en un fitxer
    :param G:
    :param output_file:
    :return:
    """
    pos = nx.spring_layout(G)
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_size=3000, node_color='lightblue', font_size=10, font_weight='bold', arrows=True)
    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='red')
    plt.savefig(output_file)
    plt.close()


def extreu_funcions_de_cel_la(cel_la, patterns):
    lines = cel_la.splitlines()
    funcions = {nom: None for nom in patterns}
    for i, line in enumerate(lines):
        for nom, pattern in patterns.items():
            if funcions[nom] is None and pattern.search(line):
                # Captura des d'aquesta línia fins al final
                funcions[nom] = "\n".join(lines[i:])
    return funcions

def delete_dataset(db_conn, name) ->bool:
    """
    Elimina un dataset de la base de dades
    :param db_conn:
    :param name:
    :return:
    """
    try:
        with db_conn.cursor() as cursor:
            sql = f"DELETE FROM dataset WHERE name='{name}'"
            cursor.execute(sql)
        db_conn.commit()
        return True
    except Exception:
        return False

def esborra_dataset_total(db_conn, name) -> bool:
    """
    Elimina un dataset i totes les seves dades associades de la base de dades
    :param db_conn:
    :param name:
    :return:
    """
    try:
        with db_conn.cursor() as cursor:
            # Elimina les dades associades
            sql = f"DELETE FROM samples s join dataset d on s.id_dataset=d.id WHERE d.name='{name}'"
            cursor.execute(sql)
            # Elimina el dataset
            sql = f"DELETE FROM dataset WHERE name='{name}'"
            cursor.execute(sql)
        db_conn.commit()
        return True
    except Exception:
        return False

def get_uci_list() -> Dict[str,int]:
    """
    Recupera la llista de datasets disponibles a UCI
    :return:
    """
    # Crea un buffer per capturar la sortida
    buffer = io.StringIO()

    # Redirigeix el print a aquest buffer
    with redirect_stdout(buffer):
        list_available_datasets()

    # Recupera tot el text com a string
    output = buffer.getvalue()
    lines = output.splitlines()
    dataset_names = {}
    for line in lines:
        # Busqeuem primer "Dataset Name" i ens quedem amb les linies que vinguin despres que no comencin amb '-'
        if line.startswith("Dataset Name"):
            continue
        if line.startswith('-') or line.strip() == '':
            continue
        # Els darrers 5 caracters son numeros i espais que corresponen al identificador del dataset. El captuem i converim a int
        try:
            id_dataset = int(line[-10:].strip())
        except:
            continue

        # Retallem els darrers 5 caracters de la linia per obtenir el nom del dataset
        dataset_name = line[:-10].strip()
        dataset_names[dataset_name] = id_dataset

    # Processa la sortida per obtenir els noms dels datasets
    return dataset_names

def get_random_dataset_name(db_conn) -> str:
    """
    Obté un nom de dataset aleatori existent a la base de dades
    :param db_conn:
    :return:
    """

    with db_conn.cursor() as cursor:
        sql = "SELECT name FROM dataset"
        cursor.execute(sql)
        row = cursor.fetchall()
        if row:
            exclude = [x[0] for x in row]
        else:
            exclude = []

    # Recupera tots els datasets
    datasets = get_uci_list()

    # Filtra els que no vols
    available = [d for d in datasets.keys() if d not in exclude]

    # Escull-ne un de forma aleatòria
    chosen = random.choice(available)

    return chosen






def carrega_funcions_des_de_notebook(notebook_path):

    with open(notebook_path, "r", encoding="utf-8") as f:
        notebook = nbformat.read(f, as_version=4)

    patterns = {
        "exists": re.compile(r"def\s+exists\s*\(.*\)\s*(->\s*\w+)?\s*:"),
        "insertVectorDataset": re.compile(r"def\s+insertVectorDataset\s*\(.*\)\s*(->\s*\w+)?\s*:")
    }

    exists_code = None
    insert_code = None

    for cell in notebook.cells:
        if cell.cell_type == "code":
            funcions = extreu_funcions_de_cel_la(cell.source, patterns)
            exists_code = exists_code or funcions["exists"]
            insert_code = insert_code or funcions["insertVectorDataset"]
            if exists_code and insert_code:
                break

    exec_globals = {}
    exec("from ucimlrepo import fetch_ucirepo", exec_globals)
    exec("import numpy as np", exec_globals)
    exec("import json", exec_globals)
    exec("import oracledb", exec_globals)
    exec("from oracledb import DB_TYPE_JSON", exec_globals)
    exec("from GABDConnect.oracleConnection import oracleConnection as orcl", exec_globals)
    if exists_code:
        exec(exists_code, exec_globals)
    if insert_code:
        exec(insert_code, exec_globals)

    return exec_globals["insertVectorDataset"], exec_globals.get("exists")


def es_main_gabd(grup: str, *, case_insensitive: bool = True, usar_fqdn: bool = True) -> bool:
    """
    Comprova si el nom de la màquina és exactament 'main.{grup}.gabd'.
    :param grup: valor del grup (p.ex. 'dev', 'uoc', 'xx')
    :param case_insensitive: ignora majúscules/minúscules si True
    :param usar_fqdn: usa el FQDN (getfqdn) en lloc del hostname curt
    """
    host_obtingut = socket.getfqdn() if usar_fqdn else socket.gethostname()
    objectiu = f"main.{grup}.gabd"
    if case_insensitive:
        return host_obtingut.lower() == objectiu.lower()
    return host_obtingut == objectiu


