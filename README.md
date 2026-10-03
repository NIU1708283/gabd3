# GABD Practical 3 - NoSQL and Distributed Databases

This repository contains the implementation and supporting files for a MongoDB-based distributed database lab. The practical work focuses on non-relational and distributed database design, replication, sharding, indexing, query execution plans, and geospatial data handling.

## Overview

The project is based on a MongoDB distributed architecture using:

- a `mongos` router
- sharded replica sets
- configuration servers
- a collection of geospatial data from Geonames

The main goal is to work with a realistic distributed database environment and analyze how partitioning, replication, and indexing affect performance and query behavior.

## Repository structure

```text
GABD_25-26_Practica_3-grup06-master/
├── README.md
├── images/
│   └── arquitectura.png
├── scripts/
│   ├── README.md
│   ├── exercici2.js
│   ├── exercici3.sh
│   ├── reinicio.sh
│   ├── testExercici1.js
│   └── usuarisRols.js
├── src/
│   ├── environment.yml
│   ├── insertGeonames.ipynb
│   ├── requirements.txt
│   ├── testUCIMongoDB.ipynb
│   └── ...
└── test/
    ├── __init__.py
    ├── reporting.py
    ├── test_db.py
    ├── utils.py
    └── ...
```

## Main objectives

The laboratory covers the following concepts:

- MongoDB sharding configuration
- replica set setup and management
- database indexing and optimization
- query plan analysis
- geospatial data insertion and retrieval
- distributed data distribution across shards
- user and role configuration
- performance evaluation of database operations

## Distributed architecture

The project follows the standard MongoDB sharded architecture, composed of three core elements:

- Shards: horizontally distributed data stores
- Config servers: metadata and shard routing information
- Router (`mongos`): coordinates client requests and forwards them to the appropriate shard

The proposed setup includes:

- one `mongos` instance on the `main` machine on port `27017`
- two shards, each implemented as a replica set distributed across the lab machines
- one configuration replica set distributed across the same machines

This design reflects a realistic distributed MongoDB environment for evaluating data distribution and query execution across partitions.

## Scripts folder

The `scripts/` directory contains automation and administration scripts used during the practical exercises, including:

- `exercici2.js`: MongoDB script for a specific exercise
- `exercici3.sh`: shell-based setup or database operation script
- `reinicio.sh`: reset script for restoring the environment
- `testExercici1.js`: validation script for the first exercise
- `usuarisRols.js`: user and role management script

The `scripts/README.md` file briefly explains the contents of that folder.

## Source and data management

The `src/` folder includes:

- Python dependency files (`requirements.txt`, `environment.yml`)
- notebook files for Geonames data insertion and optional UCI data processing
- Jupyter-based workflow for loading and validating data in MongoDB

This makes the project suitable for data ingestion and analytical testing using Python and MongoDB connectors.

## Testing and validation

The `test/` folder contains Python-based testing utilities and database validation scripts, including:

- database checks
- reporting utilities
- helper functions
- pytest-style test organization

These tests verify that the database state, configuration, and data operations meet the expected requirements of the practical assignment.

## Technologies used

- MongoDB
- Python
- Jupyter Notebook
- PyMongo
- pytest
- shell scripting
- pandas / matplotlib / scikit-learn (as listed in requirements)

## Run and setup notes

To run the project correctly, you need:

- a MongoDB cluster environment or equivalent local setup
- SSH access to the assigned machines if using the course infrastructure
- MongoDB clients such as Mongo Shell, Compass, or noSQLBooster
- the Python dependencies from `src/requirements.txt`

Before execution, the environment should be configured according to the practical exercise instructions, including:

- shard configuration
- replica set initialization
- database and collection creation
- insertion of Geonames data
- index creation and validation

## Summary

This project is a practical exercise in the design and administration of distributed NoSQL databases with MongoDB. It combines database architecture, indexing, sharding, replication, and geospatial query analysis in a realistic environment. The repository is mainly focused on learning how distributed systems manage and scale large datasets while keeping performance predictable and testable.

## Contact

This project is part of a university database course and was designed for the subject professors and students involved in the assignment.
