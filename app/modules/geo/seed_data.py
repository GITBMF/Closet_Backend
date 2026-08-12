"""Cameroon geographic reference data (seed).

Two hierarchies are seeded, matching the models in ``app.modules.geo.models``:

  * Administrative:  Region -> Division -> Subdivision   (for addresses)
  * Delivery zones:  Region -> FixedRateCity -> Neighbourhood

Completeness note (read this):
  * REGIONS  — all 10 of Cameroon's regions. Complete and authoritative.
  * DIVISIONS — all 58 official divisions (départements). Complete.
  * SUBDIVISIONS (arrondissements) — a broad, curated set. Cameroon has ~360
    and periodically creates new communes, so treat this layer as a strong
    starting point and extend it against the current official gazette if you
    need every last one. Adding entries here is safe: the seeder is idempotent
    and inserts only what is missing on the next run.
  * CITIES / NEIGHBOURHOODS — the delivery-pricing zones you are most likely to
    launch with (major towns and their well-known quarters). Extend freely.

`code` on a region is its ISO 3166-2:CM code (stable, unique). Divisions,
subdivisions and neighbourhoods are keyed by (parent, name); cities by name.
"""

from __future__ import annotations

# --- Administrative hierarchy: regions -> divisions -> subdivisions ----------
# Each region: {"code", "name", "divisions": [{"name", "subdivisions": [...]}]}

REGIONS: list[dict] = [
    {
        "code": "AD",
        "name": "Adamaoua",
        "divisions": [
            {"name": "Djérem", "subdivisions": ["Tibati", "Ngaoundal"]},
            {"name": "Faro-et-Déo", "subdivisions": ["Tignère", "Galim-Tignère", "Kontcha", "Mayo-Baléo"]},
            {"name": "Mayo-Banyo", "subdivisions": ["Banyo", "Bankim", "Mayo-Darlé"]},
            {"name": "Mbéré", "subdivisions": ["Meiganga", "Dir", "Djohong", "Ngaoui"]},
            {"name": "Vina", "subdivisions": ["Ngaoundéré I", "Ngaoundéré II", "Ngaoundéré III", "Belel", "Mbé", "Martap", "Nganha", "Nyambaka"]},
        ],
    },
    {
        "code": "CE",
        "name": "Centre",
        "divisions": [
            {"name": "Haute-Sanaga", "subdivisions": ["Nanga-Eboko", "Bibey", "Lembé-Yezoum", "Mbandjock", "Minta", "Nkoteng", "Nsem"]},
            {"name": "Lekié", "subdivisions": ["Monatélé", "Batchenga", "Ebebda", "Elig-Mfomo", "Evodoula", "Lobo", "Obala", "Okola", "Sa'a"]},
            {"name": "Mbam-et-Inoubou", "subdivisions": ["Bafia", "Bokito", "Deuk", "Kiiki", "Kon-Yambetta", "Makénéné", "Ndikiniméki", "Nitoukou", "Ombessa"]},
            {"name": "Mbam-et-Kim", "subdivisions": ["Ntui", "Mbangassina", "Ngambè-Tikar", "Ngoro", "Yoko"]},
            {"name": "Méfou-et-Afamba", "subdivisions": ["Mfou", "Awae", "Esse", "Nkolafamba", "Olanguina", "Soa"]},
            {"name": "Méfou-et-Akono", "subdivisions": ["Ngoumou", "Akono", "Bikok", "Mbankomo"]},
            {"name": "Mfoundi", "subdivisions": ["Yaoundé I", "Yaoundé II", "Yaoundé III", "Yaoundé IV", "Yaoundé V", "Yaoundé VI", "Yaoundé VII"]},
            {"name": "Nyong-et-Kéllé", "subdivisions": ["Éséka", "Biyouha", "Bondjock", "Bot-Makak", "Dibang", "Makak", "Matomb", "Messondo", "Ngog-Mapubi", "Nguibassal"]},
            {"name": "Nyong-et-Mfoumou", "subdivisions": ["Akonolinga", "Ayos", "Endom", "Mengang"]},
            {"name": "Nyong-et-So'o", "subdivisions": ["Mbalmayo", "Akoeman", "Dzeng", "Mengueme", "Ngomedzap", "Nkolmetet"]},
        ],
    },
    {
        "code": "ES",
        "name": "Est",
        "divisions": [
            {"name": "Boumba-et-Ngoko", "subdivisions": ["Yokadouma", "Gari-Gombo", "Moloundou", "Salapoumbé"]},
            {"name": "Haut-Nyong", "subdivisions": ["Abong-Mbang", "Angossas", "Atok", "Dimako", "Doumaintang", "Doumé", "Lomié", "Mboma", "Messamena", "Messok", "Mindourou", "Ngoyla", "Nguelemendouka", "Somalomo"]},
            {"name": "Kadey", "subdivisions": ["Batouri", "Kentzou", "Kette", "Mbang", "Ndélélé", "Nguélébok", "Ouli"]},
            {"name": "Lom-et-Djérem", "subdivisions": ["Bertoua I", "Bertoua II", "Bélabo", "Bétaré-Oya", "Diang", "Garoua-Boulaï", "Mandjou", "Ngoura"]},
        ],
    },
    {
        "code": "EN",
        "name": "Extrême-Nord",
        "divisions": [
            {"name": "Diamaré", "subdivisions": ["Maroua I", "Maroua II", "Maroua III", "Bogo", "Dargala", "Gazawa", "Meri", "Ndoukoula", "Petté"]},
            {"name": "Logone-et-Chari", "subdivisions": ["Kousséri", "Blangoua", "Darak", "Fotokol", "Goulfey", "Hilé-Alifa", "Logone-Birni", "Makary", "Waza", "Zina"]},
            {"name": "Mayo-Danay", "subdivisions": ["Yagoua", "Datcheka", "Gobo", "Guéré", "Kai-Kai", "Kalfou", "Kar-Hay", "Maga", "Tchatibali", "Wina"]},
            {"name": "Mayo-Kani", "subdivisions": ["Kaélé", "Guidiguis", "Mindif", "Moulvoudaye", "Moutourwa", "Porhi", "Taïbong", "Touloum"]},
            {"name": "Mayo-Sava", "subdivisions": ["Mora", "Kolofata", "Tokombéré"]},
            {"name": "Mayo-Tsanaga", "subdivisions": ["Mokolo", "Bourha", "Hina", "Koza", "Mayo-Moskota", "Mogodé", "Soulédé-Roua"]},
        ],
    },
    {
        "code": "LT",
        "name": "Littoral",
        "divisions": [
            {"name": "Moungo", "subdivisions": ["Nkongsamba I", "Nkongsamba II", "Nkongsamba III", "Baré-Bakem", "Bonaléa", "Dibombari", "Ébone", "Loum", "Manjo", "Mbanga", "Melong", "Mombo", "Njombé-Penja", "Nlonako"]},
            {"name": "Nkam", "subdivisions": ["Yabassi", "Nkondjock", "Nord-Makombé", "Yingui"]},
            {"name": "Sanaga-Maritime", "subdivisions": ["Édéa I", "Édéa II", "Dizangué", "Massock-Songloulou", "Ndom", "Ngambè", "Ngwei", "Nyanon", "Pouma"]},
            {"name": "Wouri", "subdivisions": ["Douala I", "Douala II", "Douala III", "Douala IV", "Douala V", "Douala VI"]},
        ],
    },
    {
        "code": "NO",
        "name": "Nord",
        "divisions": [
            {"name": "Bénoué", "subdivisions": ["Garoua I", "Garoua II", "Garoua III", "Bascheo", "Bibémi", "Dembo", "Gaschiga", "Lagdo", "Ngong", "Pitoa", "Touroua"]},
            {"name": "Faro", "subdivisions": ["Poli", "Beka"]},
            {"name": "Mayo-Louti", "subdivisions": ["Guider", "Figuil", "Mayo-Oulo"]},
            {"name": "Mayo-Rey", "subdivisions": ["Tcholliré", "Madingring", "Rey-Bouba", "Touboro"]},
        ],
    },
    {
        "code": "NW",
        "name": "Nord-Ouest",
        "divisions": [
            {"name": "Boyo", "subdivisions": ["Fundong", "Belo", "Bum", "Njinikom"]},
            {"name": "Bui", "subdivisions": ["Kumbo", "Jakiri", "Mbiame", "Nkum", "Noni", "Oku"]},
            {"name": "Donga-Mantung", "subdivisions": ["Nkambé", "Ako", "Misaje", "Ndu", "Nwa"]},
            {"name": "Menchum", "subdivisions": ["Wum", "Benakuma", "Furu-Awa", "Zhoa"]},
            {"name": "Mezam", "subdivisions": ["Bamenda I", "Bamenda II", "Bamenda III", "Bafut", "Bali", "Santa", "Tubah"]},
            {"name": "Momo", "subdivisions": ["Mbengwi", "Andek", "Ngie", "Njikwa", "Widikum"]},
            {"name": "Ngo-Ketunjia", "subdivisions": ["Ndop", "Babessi", "Balikumbat"]},
        ],
    },
    {
        "code": "OU",
        "name": "Ouest",
        "divisions": [
            {"name": "Bamboutos", "subdivisions": ["Mbouda", "Babadjou", "Batcham", "Galim"]},
            {"name": "Haut-Nkam", "subdivisions": ["Bafang", "Bakou", "Bana", "Bandja", "Banka", "Kekem"]},
            {"name": "Hauts-Plateaux", "subdivisions": ["Baham", "Bamendjou", "Bangou", "Batié"]},
            {"name": "Koung-Khi", "subdivisions": ["Bandjoun", "Bayangam", "Djebem"]},
            {"name": "Menoua", "subdivisions": ["Dschang", "Fokoué", "Fongo-Tongo", "Nkong-Zem", "Penka-Michel", "Santchou"]},
            {"name": "Mifi", "subdivisions": ["Bafoussam I", "Bafoussam II", "Bafoussam III"]},
            {"name": "Ndé", "subdivisions": ["Bangangté", "Bassamba", "Bazou", "Tonga"]},
            {"name": "Noun", "subdivisions": ["Foumban", "Bangourain", "Foumbot", "Kouoptamo", "Koutaba", "Magba", "Malentouen", "Massangam", "Njimom"]},
        ],
    },
    {
        "code": "SU",
        "name": "Sud",
        "divisions": [
            {"name": "Dja-et-Lobo", "subdivisions": ["Sangmélima", "Bengbis", "Djoum", "Meyomessala", "Mintom", "Oveng", "Zoétélé"]},
            {"name": "Mvila", "subdivisions": ["Ebolowa I", "Ebolowa II", "Biwong-Bané", "Biwong-Bulu", "Efoulan", "Mengong", "Mvangan", "Ngoulemakong"]},
            {"name": "Océan", "subdivisions": ["Kribi I", "Kribi II", "Akom II", "Bipindi", "Campo", "Lolodorf", "Mvengue", "Niété"]},
            {"name": "Vallée-du-Ntem", "subdivisions": ["Ambam", "Kyé-Ossi", "Ma'an", "Olamze"]},
        ],
    },
    {
        "code": "SW",
        "name": "Sud-Ouest",
        "divisions": [
            {"name": "Fako", "subdivisions": ["Limbe I", "Limbe II", "Limbe III", "Buea", "Muyuka", "Tiko", "Idenau", "West Coast"]},
            {"name": "Koupé-Manengouba", "subdivisions": ["Bangem", "Nguti", "Tombel"]},
            {"name": "Lebialem", "subdivisions": ["Menji", "Alou", "Wabane"]},
            {"name": "Manyu", "subdivisions": ["Mamfe", "Akwaya", "Eyumojock", "Tinto"]},
            {"name": "Meme", "subdivisions": ["Kumba I", "Kumba II", "Kumba III", "Konye", "Mbonge"]},
            {"name": "Ndian", "subdivisions": ["Mundemba", "Bamusso", "Ekondo-Titi", "Idabato", "Isangele", "Kombo-Abedimo", "Kombo-Itindi", "Toko"]},
        ],
    },
]


# --- Delivery zones: cities (fixed-rate) -> neighbourhoods --------------------
# Each city: {"name", "region": <region code>, "is_active", "neighbourhoods": [...]}

CITIES: list[dict] = [
    {"name": "Douala", "region": "LT", "neighbourhoods": [
        "Akwa", "Bonanjo", "Bonapriso", "Bonabéri", "Deïdo", "New Bell", "Bépanda",
        "Makepe", "Bonamoussadi", "Ndokotti", "Logbaba", "Kotto", "Yassa", "Japoma",
        "Cité SIC", "Ndogbong", "Bali", "Village", "PK8", "PK14"]},
    {"name": "Yaoundé", "region": "CE", "neighbourhoods": [
        "Bastos", "Centre Commercial", "Nlongkak", "Mvog-Mbi", "Mvan", "Mvog-Ada",
        "Nsam", "Biyem-Assi", "Mendong", "Etoudi", "Emana", "Nkolbisson", "Mokolo",
        "Briqueterie", "Essos", "Mimboman", "Ekounou", "Ngoa-Ekelle", "Melen",
        "Obili", "Nkoldongo", "Damas", "Odza"]},
    {"name": "Bafoussam", "region": "OU", "neighbourhoods": [
        "Tamdja", "Kamkop", "Djeleng", "Tougang", "Banengo", "Ndiangdam", "Famla", "Tocket"]},
    {"name": "Bamenda", "region": "NW", "neighbourhoods": [
        "Commercial Avenue", "Nkwen", "Mankon", "Ntarikon", "Old Town", "Up Station",
        "Mile 2", "Mile 4", "Bayelle", "Ntamulung", "Foncha", "Mulang", "Ngomgham", "Bambili"]},
    {"name": "Buea", "region": "SW", "neighbourhoods": [
        "Molyko", "Bonduma", "Great Soppo", "Small Soppo", "Mile 16", "Mile 17",
        "Muea", "Bokwango", "Bomaka", "Buea Town", "Bokova"]},
    {"name": "Limbe", "region": "SW", "neighbourhoods": [
        "Down Beach", "Mile 4", "Bota", "Middle Farms", "Church Street", "New Town", "Mile 1", "Mile 2"]},
    {"name": "Kumba", "region": "SW", "neighbourhoods": [
        "Fiango", "Kosala", "Buea Road", "Mbonge Road", "Station", "Three Corners", "Kumba Town"]},
    {"name": "Garoua", "region": "NO", "neighbourhoods": [
        "Plateau", "Poumpoumré", "Roumdé-Adjia", "Djamboutou", "Kollere", "Foulbéré"]},
    {"name": "Maroua", "region": "EN", "neighbourhoods": [
        "Domayo", "Djarengol", "Founangué", "Kakataré", "Pitoaré", "Palar", "Doualaré", "Hardé"]},
    {"name": "Ngaoundéré", "region": "AD", "neighbourhoods": [
        "Baladji", "Burkina", "Dang", "Mbideng", "Petit-Marché", "Bamyanga"]},
    {"name": "Bertoua", "region": "ES", "neighbourhoods": [
        "Nkolbikon", "Mokolo", "Tigaza", "Madagascar", "Kano", "Haoussa"]},
    {"name": "Ebolowa", "region": "SU", "neighbourhoods": ["Angalé", "Nko'ovos", "New-Bell", "Mvam-Essakoé"]},
    {"name": "Kribi", "region": "SU", "neighbourhoods": ["Dombé", "Afan-Mabé", "Talla", "Mboa-Manga", "Nziou", "Beach"]},
    {"name": "Édéa", "region": "LT", "neighbourhoods": ["Ekité", "Bonepoupa", "Mbanda", "Pongo"]},
    {"name": "Nkongsamba", "region": "LT", "neighbourhoods": ["Quartier Haoussa", "Bonaberi", "Ballong", "Camp Yabassi"]},
    {"name": "Loum", "region": "LT"},
    {"name": "Manjo", "region": "LT"},
    {"name": "Dschang", "region": "OU", "neighbourhoods": ["Foto", "Foréké", "Paid Ground", "Tsinkop"]},
    {"name": "Foumban", "region": "OU", "neighbourhoods": ["Njinka", "Njissé", "Mansaré"]},
    {"name": "Mbouda", "region": "OU"},
    {"name": "Bangangté", "region": "OU"},
    {"name": "Kumbo", "region": "NW", "neighbourhoods": ["Tobin", "Squares", "Mbveh", "Romajay"]},
    {"name": "Wum", "region": "NW"},
    {"name": "Mamfe", "region": "SW"},
    {"name": "Tiko", "region": "SW", "neighbourhoods": ["Long Street", "Motor Park", "Mondoni", "Likomba"]},
    {"name": "Mbalmayo", "region": "CE", "neighbourhoods": ["Nkolyem", "Abang", "Ebogo"]},
    {"name": "Bafia", "region": "CE"},
    {"name": "Sangmélima", "region": "SU"},
    {"name": "Kousséri", "region": "EN"},
    {"name": "Yagoua", "region": "EN"},
    {"name": "Guider", "region": "NO"},
    {"name": "Tibati", "region": "AD"},
    {"name": "Meiganga", "region": "AD"},
    {"name": "Batouri", "region": "ES"},
    {"name": "Yokadouma", "region": "ES"},
    {"name": "Ambam", "region": "SU"},
]
