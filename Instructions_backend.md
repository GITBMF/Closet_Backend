Pour le developpement de l'application, vous aurez besoin de la bdd.

Le serveur de la BDD est configure pour tourner sur un container (`db_closet`).

1. Copier sur vos pc a la racine du repository, les trois fichiers `.env.dev` `.env.staging` et `.env.prod` qui contiennent les informations de connexion a la BDD postgreSQL

2. Demarrer le serveur de la BDD.
    a. Installer le logiciel [Docker Desktop](https://www.docker.com/products/docker-desktop/)
    
    b. Dans le terminal de VS code executer :
    `docker compose --env-file .env.dev -d`

3. La BDD est activee et les infos de connexion sont dans le fichier `.env.dev`