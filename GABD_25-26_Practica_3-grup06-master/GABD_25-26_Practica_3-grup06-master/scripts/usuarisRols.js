var db = db.getSiblingDB('admin');

// Crear SYS
// Aquest usuari és l'únic capaç de crear altres usuaris i rols inicialment.
db.createUser({
    user: "SYS",
    pwd: "SYS",
    roles: [ { role: "root", db: "admin" } ]
});

// Autenticar com a SYS per continuar
db.auth("SYS", "SYS");


// Rol TEST: Permisos bàsics de lectura
db.createRole({
    role: "TEST",
    privileges: [
        { resource: { db: "geonames", collection: "" }, actions: [ "find" ] }
    ],
    roles: []
});

// Rol GESTOR: Permisos de lectura i escriptura
db.createRole({
    role: "GESTOR",
    privileges: [
        { resource: { db: "geonames", collection: "" }, actions: [ "find", "insert", "update", "remove" ] },
        { resource: { db: "uci", collection: "" }, actions: [ "find", "insert", "update", "remove" ] }
    ],
    roles: []
});


// Usuari per a consultes Python (Rol TEST)
db.getSiblingDB('geonames').createUser({
    user: "userPython",
    pwd: "userPython",
    roles: [ { role: "TEST", db: "admin" } ]
});

// Gestors (Rol GESTOR)
db.getSiblingDB('admin').createUser({
    user: "gestorUsuaris",
    pwd: "gestorUsuaris",
    roles: [ { role: "userAdminAnyDatabase", db: "admin" } ] // Permís per gestionar usuaris
});

db.getSiblingDB('geonames').createUser({
    user: "gestorGeonames",
    pwd: "gestorGeonames",
    roles: [ { role: "GESTOR", db: "admin" } ]
});

db.getSiblingDB('uci').createUser({
    user: "gestorUCI",
    pwd: "gestorUCI",
    roles: [ { role: "GESTOR", db: "admin" } ]
});

print("### Usuaris i Rols creats correctament ###");