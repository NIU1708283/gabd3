import time
import unittest
from GABDConnect import mongoConnection
from GABDConnect import oracleConnection as orcl, get_free_port
from pymongo.errors import OperationFailure
from typing import Optional, List, Union
import logging
import sys
from dotenv import load_dotenv
import os
#sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '/test/')))
import re
from pprint import pprint
from .utils import (  es_main_gabd)
import socket
import socks  # pip install PySocks

from .reporting import (ReportMeta, ReportBuilder, TestStatus, BuilderOptions, DictRenderOptions, autofill_meta)
import inspect
import time
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from urllib.parse import quote_plus

USED_PORTS = set()


def get_unique_free_port(port=None):
    port = port if port is not None else get_free_port()
    while port in USED_PORTS:
        port = get_free_port()
    USED_PORTS.add(port)
    return port



meta = autofill_meta(
    suite_name="Autoavaluació de la Pràctica 3",
    overrides={
        # Pots sobreescriure el que vulguis:
        # "environment": "staging",
        "header_note": "En aquest informe trobareu els elements crítics de la pràctica.",
        "footer_note": "Contacte: oriol.ramos@uab.cat",
    }
)


options = BuilderOptions(
    dict_render=DictRenderOptions(mode="auto", flatten=True, collapse_section=True),
    show_toc=True,
    show_summary=True,
    show_metrics=True,
    show_links=True,
    show_tags=False,
)

rb = ReportBuilder(meta, options)


class Practica3TestCase(unittest.TestCase):

    def _checkport(self, port: int) -> int:
        """
        Comprova si es pot obrir connexió amb MongoDB al port indicat.
        Si no, prova amb el port per defecte (27017).
        Retorna el port que ha funcionat o 0 si cap funciona.

        Nota: Si el port respon però l'autenticació falla, es considera que
        el port és vàlid (retorna el port amb error d'autenticació).
        """
        from pymongo.errors import OperationFailure, ServerSelectionTimeoutError, ConnectionFailure

        for p in [port, 27017]:
            try:
                with mongoConnection(user=self.sys_user, pwd=self.sys_pwd,
                                     hostname=self.main_mongo_server, port=p,
                                     ssh_data=self.ssh_server, db=self.db) as client:
                    # Intentem una operació senzilla per validar connexió
                    client.conn["admin"].command("ping")
                    return p  # Connexió OK

            except OperationFailure as e:
                # Error d'autenticació: el port funciona però les credencials són incorrectes
                if "Authentication failed" in str(e) or "auth failed" in str(e).lower():
                    print(f"⚠️  Port {p}: MongoDB respon però l'autenticació ha fallat")
                    return p  # Retornem el port perquè el servidor MongoDB està accessible
                # Altres errors d'operació (no relacionats amb autenticació)
                continue

            except (ServerSelectionTimeoutError, ConnectionFailure) as e:
                # Error de connexió: el port no respon o MongoDB no està accessible
                print(f"❌ Port {p}: No es pot connectar amb MongoDB")
                continue

            except Exception as e:
                # Qualsevol altre error inesperat
                print(f"⚠️  Port {p}: Error inesperat: {type(e).__name__}: {e}")
                continue

        return 0  # Cap port ha funcionat


    def setUp(self):

        load_dotenv()  # Carrega el fitxer .env
        # Llegir credencials del workflow si no hi ha fitxer local
        ssh_host = os.environ.get("SSH_HOST", "dcccluster.uab.cat")
        ssh_user = os.environ.get("SSH_USER", "student")
        ssh_port = int(os.environ.get("SSH_PORT", 22))
        ssh_password = os.environ.get("SSH_PASSWORD", "student")
        self.grup = grup = os.environ.get("GRUP", "grup00")

        if not es_main_gabd(grup):
            self.ssh_server = {
                'ssh': ssh_host,
                'user': ssh_user,
                'pwd': ssh_password,
                'port': ssh_port
            }
        else:
            self.ssh_server = None

        self.oracle_server = f"oracle-1.{grup}.gabd"
        self.main_mongo_server = f"main.{grup}.gabd"



        self.port = 1521
        self.serviceName = "FREEPDB1"
        self.mode="SYSDBA"

        self.user = "GestorUCI"
        self.pwd = grup
        self.db="Test"

        self.sys_user = "SYS"
        self.sys_pwd = "SYS"

        self.mongo_port = self._checkport(37017)

    def tearDown(self):
        # Aquí alliberes túnels després de cada test
        orcl.close_all_tunnels()
        USED_PORTS.clear()

    def test_autenticacio_i_usuaris_roles(self):
        """
        Comprovem si el servidor MongoDB principal té l'autenticació activada i si els usuaris i rols definits al script s'han creat correctament.
        """

        users_expected = {
            "userPython": "TEST",
            "gestorUsuaris": "GESTOR",
            "gestorGeonames": "GESTOR"
        }
        roles_expected = ["TEST", "GESTOR"]

        start = time.perf_counter()
        status_for_report = TestStatus.FAIL
        status_note = None
        metrics = {}
        metrics['Puntuació'] = 0
        puntuacio_total = 0
        activada = True
        report = {}


        try:
            # 1) Intentem connectar sense credencials (hauria de fallar si autenticació activada)
            with mongoConnection(hostname=self.main_mongo_server, port=self.mongo_port, ssh_data=self.ssh_server,
                                 db=self.db) as client:
                db = client.conn["admin"]
                client.test_connection()
                status = db.command("connectionStatus")
                report['Connection Status'] = status

            # Si arriba aquí, autenticació NO activada
            metrics['Autenticació'] = "No s'ha activat l'autenticació."
            activada = False

        except OperationFailure as e:
            # Autenticació activada
            status_for_report = TestStatus.PASS
            status_note = str(e)
            puntuacio_total = 0.5

        except Exception as e:
            if self.mongo_port == 0:
                status_for_report = TestStatus.FAIL
                status_note = "No s'ha pogut connectar al servidor MongoDB en cap port."
                activada = False
            else:
                status_for_report = TestStatus.ERROR
                status_note = f"Excepció: {type(e).__name__}: {e}"
                raise

        if activada:
            try:
                # 2) Connectem amb credencials SYS
                with mongoConnection(user=self.sys_user, pwd=self.sys_pwd, hostname=self.main_mongo_server,
                                     port=self.mongo_port, ssh_data=self.ssh_server, db=self.db) as client:
                    db = client.conn["admin"]
                    status = db.command("connectionStatus")
                    report['Connection Status'] = str(status)
                    metrics['Autenticació'] = "S'ha activat l'autenticació."

                    # 3) Validem rols
                    roles_info = db.command("rolesInfo", showBuiltinRoles=False)
                    roles = {r["role"]: r for r in roles_info["roles"]}
                    roles_ok = all(role in roles for role in roles_expected)

                    # 4) Validem usuaris
                    users_info = db.command("usersInfo")
                    users = {u["user"]: u for u in users_info["users"]}
                    users_ok = all(user in users and any(r["role"] == role for r in users[user]["roles"])
                                   for user, role in users_expected.items())

                    report['Rols trobats'] = str(list(roles.keys()))
                    report['Usuaris trobats'] = str(list(users.keys()))
                    if roles_ok and users_ok:
                        puntuacio_total += 0.5
                        status_for_report = TestStatus.PASS
                        status_note = "Autenticació i usuaris/rols OK."
                    else:
                        status_for_report = TestStatus.FAIL
                        status_note = "Autenticació OK però usuaris/rols incorrectes."

            except AssertionError as e:
                status_for_report = TestStatus.FAIL
                status_note = str(e)
                puntuacio_total = 0
                metrics['Autenticació'] = "No s'ha activat l'autenticació."
                #report['Connection Status'] =str(e)
                activada = False

        duration = time.perf_counter() - start
        metrics['Puntuació'] = puntuacio_total

        rb.add_test(
            id="ex_1",
            title="Exercici 1. Autenticació i validació d'usuaris/rols MongoDB",
            general_text=inspect.getdoc(self.test_autenticacio_i_usuaris_roles),
            status=status_for_report,
            status_note=status_note or "Connexió OK." if status_for_report == TestStatus.PASS else status_note,
            duration_s=duration,
            metrics=metrics,
            report=report
        )

    def test_replicaset(self):
        """
        Comprovem si s'ha creat correctament el replicaset amb els nodes i ports indicats.

        """

        start = time.perf_counter()
        status_for_report = TestStatus.PASS
        status_note = None
        metrics = {}
        metrics['Puntuació'] = 0

        port = 37017

        # port = self._checkport(port)

        nodes = [
            f"main.{self.grup}.gabd:{port}",
            f"mongo-1.{self.grup}.gabd:{port}",
            f"mongo-2.{self.grup}.gabd:{port}"
        ]
        markdown_output = ""

        try:
            with mongoConnection(user=self.sys_user, pwd=self.sys_pwd, hostname=self.main_mongo_server,
                                 port=port, ssh_data=self.ssh_server, db=self.db) as client:

                db = client.conn["admin"]
                status = db.command("replSetGetStatus")

                member_names = [m['name'] for m in status['members']]
                missing_nodes = [n for n in nodes if n not in member_names]

                markdown_output += "## Replica Set Status\n"
                markdown_output += f"**Replica Set Name:** {status['set']}\n\n"
                markdown_output += "### Members:\n"

                metrics['total_members'] = len(status['members'])
                metrics['PRIMARY'] = 0
                metrics['SECONDARY'] = 0
                metrics['ARBITER'] = 0

                for member in status['members']:
                    state = member['stateStr']
                    name = member['name']
                    emoji = "⚪"
                    if state == "PRIMARY":
                        emoji = "🟢"
                        metrics['PRIMARY'] += 1
                    elif state == "SECONDARY":
                        emoji = "🔵"
                        metrics['SECONDARY'] += 1
                    elif state == "ARBITER":
                        emoji = "🟡"
                        metrics['ARBITER'] += 1

                    markdown_output += f"- {name} ({emoji} **{state}**)\n"

                if missing_nodes:
                    markdown_output += f"\n**Warning:** Missing expected nodes: {', '.join(missing_nodes)}\n"


        except OperationFailure as e:
            if "not running with --replSet" in str(e):
                markdown_output = "## Standalone Instance\n\nEstàs connectat a un **Standalone** (no hi ha replica set)."
                metrics['total_members'] = 1
            else:
                markdown_output = f"## Error\n\nError detectant el tipus d'instància: {str(e)}"
                metrics['error'] = str(e)

            print("Markdown Output:\n", markdown_output)

            status_for_report = TestStatus.FAIL
            status_note = str(e)
            # raise  # molt important: re-llançar perquè unittest marqui FAIL

        except Exception as e:
            status_for_report = TestStatus.ERROR
            status_note = f"Excepció: {type(e).__name__}: {e}"
            # raise  # re-llança perquè unittest marqui ERROR

        finally:
            duration = time.perf_counter() - start
            # metrics['Puntuació Total'] = puntuacio_total / len(users)  # exemple de mètrica addicional
            rb.add_test(
                id="ex_2",
                title="Exercici 2. Replica Set",
                general_text=inspect.getdoc(self.test_replicaset) + "\n\n" + markdown_output,  # <-- docstring com a text,
                status=status_for_report,
                status_note=status_note or "Connexió OK." if status_for_report == TestStatus.PASS else status_note,
                duration_s=duration,
                metrics=metrics,
                # report= resultat, #... (si vols adjuntar-hi un dict amb més detall)
            )

    def test_sharding(self):
        """
        Comprovem si s'ha creat correctament el sharding amb els shards, config servers i mongos indicats.
        """

        start = time.perf_counter()
        status_for_report = TestStatus.PASS
        status_note = None
        metrics = {'Puntuació': 0}
        markdown_output = ""

        port_rs0 = 37017
        port_rs1 = 47017
        port_cfg = 57017

        expected_shards = {
            "rs0": [f"main.{self.grup}.gabd:{port_rs0}",
                    f"mongo-1.{self.grup}.gabd:{port_rs0}",
                    f"mongo-2.{self.grup}.gabd:{port_rs0}"],
            "rs1": [f"main.{self.grup}.gabd:{port_rs1}",
                    f"mongo-1.{self.grup}.gabd:{port_rs1}",
                    f"mongo-2.{self.grup}.gabd:{port_rs1}"]
        }

        port = self._checkport(port_rs0)

        expected_config_servers = [f"main.{self.grup}.gabd:{port_cfg}",
                                   f"mongo-1.{self.grup}.gabd:{port_cfg}",
                                   f"mongo-2.{self.grup}.gabd:{port_cfg}"]

        try:
            with mongoConnection(user=self.sys_user, pwd=self.sys_pwd,
                                 hostname=self.main_mongo_server, port=port,
                                 ssh_data=self.ssh_server, db=self.db) as client:

                db = client.conn["admin"]

                # ✅ Comprovem si estem connectats via mongos
                is_mongos = db.command("isdbgrid")  # Retorna {'isdbgrid': 1} si és mongos
                if not is_mongos.get("isdbgrid"):
                    markdown_output += "### ❌ No estàs connectat via mongos\n"
                    markdown_output += "Aquest test requereix connexió a **mongos** per validar sharding.\n"
                    status_for_report = TestStatus.FAIL
                    status_note = "Connexió no és mongos."
                else:
                    markdown_output += "### ✅ Connexió via mongos detectada\n\n"

                    # ✅ Obtenim informació dels shards
                    shards_info = db.command("listShards")
                    markdown_output += f"**Total Shards:** {len(shards_info['shards'])}\n\n"
                    metrics['total_shards'] = len(shards_info['shards'])

                    # ✅ Validació shards
                    for shard in shards_info['shards']:
                        shard_name = shard['_id']
                        hosts = shard['host'].split('/')[1].split(',')
                        markdown_output += f"#### 🗂 Shard: {shard_name}\n"
                        for h in hosts:
                            markdown_output += f"- {h} (🟢 OK)\n" if h in expected_shards.get(shard_name,
                                                                                             []) else f"- {h} (⚪ Extra)\n"

                        # Comprovar nodes esperats
                        if shard_name in expected_shards:
                            missing = [n for n in expected_shards[shard_name] if n not in hosts]
                            if missing:
                                markdown_output += f"**⚠️ Warning:** Missing nodes in {shard_name}: {', '.join(missing)}\n"

                    # ✅ Validació config servers
                    cfg_status = db.command("getCmdLineOpts")  # Comprovem configdb
                    configdb = cfg_status.get("parsed", {}).get("sharding", {}).get("configDB", "")
                    markdown_output += f"\n**ConfigDB:** {configdb}\n"
                    for cfg in expected_config_servers:
                        if cfg not in configdb:
                            markdown_output += f"**⚠️ Warning:** Missing config server: {cfg}\n"

        except OperationFailure as e:
            markdown_output = f"### ❌ Error\n\nError detectant sharding: {str(e)}"
            status_for_report = TestStatus.FAIL
            status_note = str(e)

        except Exception as e:
            status_for_report = TestStatus.ERROR
            status_note = f"Excepció: {type(e).__name__}: {e}"

        finally:
            duration = time.perf_counter() - start
            rb.add_test(
                id="ex_3",
                title="Exercici 3. Sharding",
                general_text=inspect.getdoc(self.test_sharding) + "\n\n" + markdown_output,
                status=status_for_report,
                status_note=status_note or "Connexió OK." if status_for_report == TestStatus.PASS else status_note,
                duration_s=duration,
                metrics=metrics
            )

    #
    # def test_datasets(self):
    #     """
    #     Comprovem que els datasets indicats a l'enunciat estan correctament inserits a la base de dades. Mirem que les dades del dataset estan a la taula DATASET, que el nombre de mostres és correcte a la taula SAMPLES i que s'han inserit correctament.
    #     """
    #
    #     UCI_datasets = [
    #         (1, 'Iris', 4, 3, {'source': 'UCI', 'url': 'https://archive.ics.uci.edu/ml/datasets/iris'}),
    #         (2, 'Ionosphere', 34, 2, {'source': 'UCI', 'url': 'https://archive.ics.uci.edu/ml/datasets/ionosphere'}),
    #         (3, 'Breast Cancer Wisconsin (Diagnostic)', 10, 2, {'source': 'UCI', 'url': 'https://archive.ics.uci.edu/ml/datasets/breast+cancer+wisconsin+(diagnostic)'}),
    #         (4,'Letter Recognition',16,26,{'source':'UCI','url':'https://archive.ics.uci.edu/ml/datasets/letter+recognition'}),
    #     ]
    #
    #
    #     start = time.perf_counter()
    #     status_for_report = TestStatus.PASS
    #     status_note = None
    #     metrics = {}
    #
    #     try:
    #
    #         db = orcl(user=self.user, passwd=self.pwd, hostname=self.oracle_server,
    #                   ssh_data=self.ssh_server, serviceName=self.serviceName)
    #
    #         with db.open() as db_conn:
    #             report, status = check_datasets(db_conn, [ds[1] for ds in UCI_datasets])
    #
    #
    #         # Calculem el score final com a mitja dels scores individuals
    #         metrics['Puntuació Final'] = sum([item['Score'] for item in report.values()]) / len(report)
    #         #pprint(report)
    #
    #         # Assert that all datasets are present
    #         self.assertEqual(True, status)  # add assertion here
    #
    #     except AssertionError as e:
    #         status_for_report = TestStatus.FAIL
    #         status_note = str(e)
    #         raise  # molt important: re-llançar perquè unittest marqui FAIL
    #     except Exception as e:
    #         status_for_report = TestStatus.ERROR
    #         status_note = f"Excepció: {type(e).__name__}: {e}"
    #         raise  # re-llança perquè unittest marqui ERROR
    #     finally:
    #         duration = time.perf_counter() - start
    #         rb.add_test(
    #             id="ex_2.1",
    #             title="Exercici 2.1",
    #             general_text=inspect.getdoc(self.test_datasets),
    #             status=status_for_report,
    #             status_note=status_note,
    #             duration_s=duration,
    #             metrics=metrics,
    #             report={'Datasets':UCI_datasets,**report},
    #             level=2
    #         )
    #
    # def test_estructura_completa_db(self):
    #     """
    #     Obtenim totes les taules de la base de dades i comprovem que tenen l'estructura correcta. El resultat de l'analisis el trobareu a la Figura \ref{fig:esquema}.
    #     :return:
    #     """
    #
    #     start = time.perf_counter()
    #     status_for_report = TestStatus.PASS
    #     status_note = None
    #     metrics = {}
    #
    #     try:
    #
    #         db = orcl(user=self.user, passwd=self.pwd, hostname=self.oracle_server,
    #                   ssh_data=self.ssh_server, serviceName=self.serviceName)
    #
    #         with db.open() as db_conn:
    #             G = obtain_esquema(db_conn, schema=self.user )
    #
    #             draw_esquema(G, output_file=f"{rb.get_report_path()}/esquema_{self.user}.png")
    #             images = {
    #                 "schema": {"label": "fig:esquema", "path": f"esquema_{self.user}.png",
    #                            "caption": f"""Esquema de la BD de la UCI per grup {self.user}. Cada node representa una
    #                            taula i les fletxes les relacions FK entre elles."""},
    #             }
    #             status = True
    #
    #         self.assertEqual(True, status)  # add assertion here
    #
    #     except AssertionError as e:
    #         status_for_report = TestStatus.FAIL
    #         status_note = str(e)
    #         raise  # molt important: re-llançar perquè unittest marqui FAIL
    #     except Exception as e:
    #         status_for_report = TestStatus.ERROR
    #         status_note = f"Excepció: {type(e).__name__}: {e}"
    #         raise  # re-llança perquè unittest marqui ERROR
    #     finally:
    #         duration = time.perf_counter() - start
    #         rb.add_test(
    #             id="ex_3",
    #             title="Exercici 3",
    #             general_text=inspect.getdoc(self.test_estructura_completa_db),
    #             status=status_for_report,
    #             status_note=status_note,
    #             duration_s=duration,
    #             metrics=metrics,
    #             images=images
    #         )
    #
    #
    # # Exemple de test
    # def test_insert_dataset(self):
    #     """
    #     Comprovem que la funció d'inserció del notebook inserData funcioni correctament.
    #     """
    #
    #
    #
    #     start = time.perf_counter()
    #     status_for_report = TestStatus.PASS
    #     status_note = None
    #     metrics = {}
    #     insertVectorDataset, _ = carrega_funcions_des_de_notebook(f"{rb.get_report_path()}/../src/insertData.ipynb")
    #     name = "Iris"
    #     metrics['Puntuació'] = 0
    #     report = {}
    #
    #     try:
    #         db = orcl(user=self.user, passwd=self.pwd, hostname=self.oracle_server,
    #                   ssh_data=self.ssh_server, serviceName=self.serviceName)
    #
    #         with db.open() as db_conn:
    #             name = get_random_dataset_name(db_conn)
    #             res = insertVectorDataset(db_conn, name)
    #             report, status_1 = check_datasets(db_conn, name)
    #             esborrat = delete_dataset(db_conn, name)
    #             if esborrat:
    #                 report, status_2 = check_datasets(db_conn, name)
    #                 if status_2:
    #                     esborra_dataset_total(db_conn, name)
    #
    #
    #         self.assertEqual(True, res)  # add assertion here
    #         metrics['insertVectorDataset'] = 1 if res else 0
    #         self.assertEqual(True, status_1)  # add assertion here
    #         metrics[f'Dataset {name}'] = "S'ha inserit correctament" if status_1 else "No s'ha inserit correctament"
    #         self.assertEqual(False, status_2)  # add assertion here
    #         metrics[f'Dataset {name} esborrat'] = "S'ha esborrat correctament" if not status_2 else "No s'ha esborrat correctament"
    #         metrics['Puntuació Final'] = (res + status_1 + (not status_2) )/3.0
    #
    #     except AssertionError as e:
    #         status_for_report = TestStatus.FAIL
    #         status_note = str(e)
    #         report = {'missatge': f'La funció no ha inserit correctament el dataset {name}.', **report}
    #         raise  # molt important: re-llançar perquè unittest marqui FAIL
    #
    #     except Exception as e:
    #         status_for_report = TestStatus.ERROR
    #         status_note = f"Excepció: {type(e).__name__}: {e}"
    #         raise  # re-llança perquè unittest marqui ERROR
    #
    #     finally:
    #         duration = time.perf_counter() - start
    #         rb.add_test(
    #             id="ex_2.2",
    #             title="Exercici 2.2",
    #             general_text=inspect.getdoc(self.test_insert_dataset),
    #             status=status_for_report,
    #             status_note=status_note,
    #             duration_s=duration,
    #             metrics=metrics,
    #             report=report,
    #         )
    #
    #


def tearDownModule():
    #rb.set_order_by_ids(["ex_1", "ex_2", "ex_2.1", "ex_3"])
    rb.set_order_by_ids(["ex_1", "ex_2", "ex_3"])
    rb.meta.file_name = f'Avaluacio{os.environ.get("GRUP", "grup00")}'
    rb.to_markdown()
    #print(md)
    rb.save()
    #rb.to_html().save("Avaluacio.html")

    # HTML (amb CSS opcional)
    #css = "body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif; max-width: 900px; margin: 2rem auto; line-height:1.5;} h1,h2,h3{margin-top:2rem}"
    #html = rb.to_html(css=css)

    #with open("informe.html", "w", encoding="utf-8") as f:
    #    f.write(html)

    # LaTeX
    # tex = rb.to_latex()

    # PDF (escriu directament al fitxer indicat)
    # pdf_path = rb.to_pdf("informe.pdf", engine="pdflatex", runs=1, keep_tex=True)


if __name__ == '__main__':
    unittest.main()





