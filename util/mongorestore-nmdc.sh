#!/bin/bash
# Execute from repo root dir:
# $ export $(grep -v '^#' .env.localhost | xargs)
# $ ./util/mongorestore-nmdc.sh
mongorestore -h $MONGO_HOST -u $MONGO_USERNAME -p $MONGO_PASSWORD --authenticationDatabase=admin \
     --gzip --drop \
    $HOME/nmdcdb-mongodump/nmdcdb/2024-07-29_20-12-07/