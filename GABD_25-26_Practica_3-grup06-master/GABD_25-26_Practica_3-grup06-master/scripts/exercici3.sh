##### FASE 1 #####

# Aturar brucament rs0:
pkill -9 mongod
rm -f /data/db/mongod.lock

# Crear directoris:
mkdir -p /home/student/RepSet-1
mkdir -p /home/student/configReplSet

# Assegurar permisos
chmod 700 /home/student/RepSet-1
chmod 700 /home/student/configReplSet

# Crear fitxers de configuració:
# Shard 1 (rs0 - Port 37017)
    cat > /data/configdb/shard1.conf <<EOF
    systemLog:
    destination: file
    path: /data/db/mongod.log
    logAppend: true
    storage:
    dbPath: /data/db
    wiredTiger:
        engineConfig:
        cacheSizeGB: 0.5
    net:
    bindIpAll: true
    port: 37017
    security:
    authorization: enabled
    keyFile: /home/student/ssl/mongodb.pem
    replication:
    replSetName: rs0
    sharding:
    clusterRole: shardsvr
    processManagement:
    fork: false
EOF
    
# Shard 2 (rs1 - Port 47017)
    cat > /data/configdb/shard2.conf <<EOF
    systemLog:
    destination: file
    path: /home/student/RepSet-1/mongod.log
    logAppend: true
    storage:
    dbPath: /home/student/RepSet-1
    wiredTiger:
        engineConfig:
        cacheSizeGB: 0.5
    net:
    bindIpAll: true
    port: 47017
    security:
    authorization: enabled
    keyFile: /home/student/ssl/mongodb.pem
    replication:
    replSetName: rs1
    sharding:
    clusterRole: shardsvr
    processManagement:
    fork: false
EOF

# Config Server
    cat > /data/configdb/config.conf <<EOF
    systemLog:
    destination: file
    path: /home/student/configReplSet/mongod.log
    logAppend: true
    storage:
    dbPath: /home/student/configReplSet
    wiredTiger:
        engineConfig:
        cacheSizeGB: 0.5
    net:
    bindIpAll: true
    port: 57017
    security:
    authorization: enabled
    keyFile: /home/student/ssl/mongodb.pem
    replication:
    replSetName: configReplSet
    sharding:
    clusterRole: configsvr
    processManagement:
    fork: false
EOF
##############################

##### FASE 2: ENGEGADA DELS SERVEIS (Executar a: main, mongo-1, mongo-2) #####
# NOTA: Com que 'fork' és false, cal usar TMUX. Obre tmux i crea 3 finestres.

# Finestra 1: Arrencar Shard 1
mongod -f /data/configdb/shard1.conf

# Finestra 2 (Ctrl+B, C): Arrencar Shard 2
mongod -f /data/configdb/shard2.conf

# Finestra 3 (Ctrl+B, C): Arrencar Config Server
mongod -f /data/configdb/config.conf

# Surt deixant-ho corrent (Ctrl+B, D)
# Verifica que hi hagi 3 processos: ps -ax | grep mongod

##############################

##### FASE 3: INICIALITZACIÓ DE RÈPLIQUES (Executar NOMÉS a: main) #####
# Aquí inicialitzem rs1 i configReplSet. 
# rs0 ja hauria d'estar inicialitzat de l'exercici anterior, però si calgués, es faria igual.

# 1. Inicialitzar Shard 2 (rs1)
mongosh --port 47017 --eval 'rs.initiate({
  _id: "rs1",
  members: [
    { _id: 0, host: "main.grup06.gabd:47017" },
    { _id: 1, host: "mongo-1.grup06.gabd:47017" },
    { _id: 2, host: "mongo-2.grup06.gabd:47017" }
  ]
})'

# 2. Inicialitzar Config Server (configReplSet)
mongosh --port 57017 --eval 'rs.initiate({
  _id: "configReplSet",
  configsvr: true,
  members: [
    { _id: 0, host: "main.grup06.gabd:57017" },
    { _id: 1, host: "mongo-1.grup06.gabd:57017" },
    { _id: 2, host: "mongo-2.grup06.gabd:57017" }
  ]
})'

##############################

##### FASE 4: ROUTER I SHARDING (Executar NOMÉS a: main) #####

# 1. Arrencar el Mongos (Router)
# RECOMANACIÓ: Fes-ho dins d un tmux nou o background (&)
mongos --configdb configReplSet/main.grup06.gabd:57017,mongo-1.grup06.gabd:57017,mongo-2.grup06.gabd:57017 \
--keyFile /home/student/ssl/mongodb.pem \
--bind_ip_all --port 27017 &

# Espera uns segons que arrenqui...
sleep 10

# 2. Configurar el Cluster (Afegir Shards)
# Connectem al router (27017) amb usuari SYS (si ja existeix a rs0, mongos el detectarà quan s'afegeixi)
# Si dona error d auth al principi, prova sense -u/-p fins que s afegeixi el primer shard.

mongosh --port 27017 -u SYS -p SYS --authenticationDatabase admin --eval '
  // Afegir Shard 1 (rs0)
  sh.addShard("rs0/main.grup06.gabd:37017,mongo-1.grup06.gabd:37017,mongo-2.grup06.gabd:37017");
  
  // Afegir Shard 2 (rs1)
  sh.addShard("rs1/main.grup06.gabd:47017,mongo-1.grup06.gabd:47017,mongo-2.grup06.gabd:47017");

  // Activar Sharding per la BD geonames
  sh.enableSharding("geonames");

  // Mostrar estat final
  printjson(sh.status());
'