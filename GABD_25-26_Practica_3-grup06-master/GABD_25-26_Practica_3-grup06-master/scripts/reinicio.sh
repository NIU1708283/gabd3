# comandos para cada servidor mongo (main, mongo-1, mongo-2)
# conectar (menos main)
ssh student@mongo-{NUMERO}.grup06.gabd

# parar por la buenas el servidor
mongod --shutdown --dbpath /data/db
# si se queda pillado, matar el proceso (descomentar las líneas posteriores)
# pkill -9 mongod
# rm /data/db/mongod.lock

# verificar que no queda nada
ps -ax | grep mongod

# iniciar el servidor
# 1. Abrir tmux (solo main)
tmux

# 1.2 Para las otras máquinas, conectarse a main y desde ahí abrir tmux o en pestañas nuevas
# ssh student@mongo-{NUMERO}.grup06.gabd

# 2. Arrancar servidor
mongod -f /data/configdb/mongo_autenticat.conf

# 3. Salir del tmux sin cerrar el proceso
# Pulsa [Ctrl] + [B], suelta las teclas, y pulsa [D].