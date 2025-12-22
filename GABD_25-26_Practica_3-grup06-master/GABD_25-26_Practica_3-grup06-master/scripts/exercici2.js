var config = {
    _id: "rs0",
    members: [
        { _id: 0, host: "main.grup06.gabd:37017", priority: 2 }, // Donem prioritat a main
        { _id: 1, host: "mongo-1.grup06.gabd:37017" },
        { _id: 2, host: "mongo-2.grup06.gabd:37017" }
    ]
};

print("### Inicialitzant el Replica Set rs0... ###");

try {
    var result = rs.initiate(config);
    printjson(result);
} catch (e) {
    print("Error retornat: " + e + " 'already initialized'= podem continuar");
}

print("### Estat Actual ###");
printjson(rs.status());