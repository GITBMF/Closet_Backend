# CLOS|ET - Backend

Backend de l'application mobile **CLOS|ET**, architecturé pour être modulaire, maintenable et prêt pour la production (VPS Hostinger puis migration Cloud).

---

## 🏗️ Arboressence du Projet (Repository Git)

```
closet-backend/
│
├── alembic/                # Versions et migrations de la base de données PostgreSQL
├── app/                    # Code source principal de l'application Python
│   ├── api/                # Les routes (endpoints) par domaine (auth, items, etc.)
│   ├── conf/               # Configuration globale et chargement des variables d'environnement (.env)
│   ├── models/             # Modèles de données ORM (SQLAlchemy) - Représentation des tables BDD
│   ├── schemas/            # Validation des contrats de données entrantes/sortantes (Pydantic)
│   ├── services/           # Logique métier pure (isolée de la plomberie réseau)
│   └── main.py             # Point d'entrée de l'application (FastAPI)
│
├── tests/                  # Tests unitaires et d'intégration
├── scripts/                # Scripts utilitaires (ex: scripts de backup, seed)
├── .env.example            # Modèle des variables d'environnement requises
├── docker-compose.yml      # Orchestration des containers Docker
├── Dockerfile              # Instructions pour packager l'API Backend
└── README.md               # Documentation technique du repo

```
## 🐳Infrastructure & Containers Docker

L'application repose sur 3 containers interconnectés via Docker Compose pour garantir une reproductibilité parfaite entre l'environnement de développement, le VPS Hostinger et le futur Cloud :

* **`nginx`**(Le Portier / Reverse Proxy)

Rôle : 
-	Renvoie les requetes vers le bon port,
-	Gere le chiffrement SSL et surtout les connexions simultanees massives et lentes
-->	Evite que l’API soit bombardee de requetes bidons
En le mettant dans Docker dès maintenant, le setup réseau sera rigoureusement le même le jour où on migrera vers le Cloud ou vers un autre Serveur

* **backend**(L'API Python / FastAPI)

Rôle : Il héberge le code python de l’API, traite les requêtes de l'application mobile et expose les différentes routes (/users, /items, etc.) qui agissent comme des aiguillages pour exécuter la bonne logique métier.

* **db**(Base de Données PostgreSQL)

Rôle : Il stocke toutes les données relationnelles de l'application de manière isolée, 
 garantir l'intégrité et faciliter les sauvegardes (pg_dump).
