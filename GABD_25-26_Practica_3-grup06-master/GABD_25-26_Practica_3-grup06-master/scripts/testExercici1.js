var db = db.getSiblingDB('geonames');

print("### Provant accés de lectura(OK): ###");
try {
    var count = db.geonames.countDocuments({});
    print("Count èxit: " + count);
} catch (e) {
    print("Error de lectura: " + e);
}

print("### Provant accés d'escriptura(ERROR): ###");
try {
    db.geonames.insertOne({test: 1});
    print("ERROR: userPython ha pogut escriure");
} catch (e) {
    print("Èxit: Escriptura denegada correctament (" + e.codeName + ")");
}