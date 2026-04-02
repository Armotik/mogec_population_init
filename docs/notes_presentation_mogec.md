# Notes de presentation MOGEC

## Contexte

Cette note est faite pour une presentation devant mon encadrante et les autres membres du projet MOGEC.
L'objectif n'est pas de tout detailler techniquement, mais d'expliquer clairement :

- le probleme traite ;
- ce que j'ai construit ;
- comment le pipeline fonctionne ;
- ce que les resultats montrent ;
- ce que le modele ne permet pas d'affirmer.

---

## Version courte a dire au debut

Bonjour.

Aujourd'hui, je vais vous presenter l'avancement de mon travail sur l'initialisation spatio-temporelle de la population pour MOGEC, appliquee au cas de Batz-sur-Mer.

L'idee generale est de produire un etat initial exploitable dans GAMA, c'est-a-dire une repartition plausible de la population dans les batiments, puis une evolution de cette presence sur 24 heures selon un scenario defini.

Le but n'est pas de reconstruire exactement la realite terrain personne par personne, mais de proposer une reconstruction coherente, parametree et tracable, utile pour la simulation.

---

## Trame de presentation conseillee

## 1. Le probleme

Ce que je cherche a faire, c'est repondre a une question simple :

"A une heure donnee, dans un scenario donne, combien de personnes sont presentes dans chaque batiment ou zone pertinente de la commune ?"

Cette question est importante pour MOGEC parce que la simulation a besoin d'un etat initial credible avant de lancer les dynamiques ou d'etudier un evenement comme une submersion.

Phrase utile :

"Le projet ne se limite pas a une carte de population residentielle. Il cherche a produire une population localisee dans l'espace et evolutive dans le temps."

## 2. Mon approche

J'ai construit un pipeline Python qui assemble plusieurs etapes :

1. charger les frontieres d'etude et les donnees batimentaires ;
2. filtrer et preparer les batiments ;
3. repartir la population residentielle issue du carroyage dans les batiments ;
4. ajouter des composantes non residentielles quand elles sont pertinentes ;
5. generer des profils et des roles dans les foyers ;
6. attribuer des destinations principales ;
7. construire une matrice horaire sur 24 heures ;
8. exporter le resultat dans un format exploitable par GAMA.

Phrase utile :

"Mon travail a donc ete de passer d'un ensemble de donnees heterogenes a un etat initial spatialise, scenario-dependant et reutilisable."

## 3. Le point important : ce n'est pas un seul resultat, c'est un moteur de scenarios

Le projet est parametre par des fichiers YAML.

Cela permet de faire varier :

- l'heure de reference ;
- le jour de la semaine ;
- la periode scolaire ou de vacances ;
- la saison ;
- la meteo ;
- le niveau d'alerte ;
- certains parametres residentiels, touristiques ou commerciaux.

Phrase utile :

"Autrement dit, je n'ai pas seulement produit une carte, j'ai mis en place un moteur de generation qui peut produire plusieurs etats initiaux selon le contexte."

## 4. Ce que produit concretement le pipeline

Le pipeline produit un GeoPackage exploitable dans GAMA avec notamment :

- un identifiant stable par batiment ;
- une population initiale `pop_t0` ;
- des colonnes horaires `pop_h0` a `pop_h23` ;
- des attributs de roles ;
- des attributs d'audit pour garder la trace des hypotheses et corrections.

Je peux dire aussi que l'export actuel correspond au scenario :

- `xynthia_winter_night_02h`
- heure de reference : `2 h`

Et sur cet export, on obtient :

- `4 779` batiments modelises ;
- `2 269` batiments occupes a `T0` ;
- `3 726` personnes presentes a `T0` ;
- `361` scolaires ;
- `1 580` seniors ;
- `578` actifs locaux ;
- `919` actifs navetteurs.

Phrase utile :

"Ces chiffres ne sont pas juste des agregats globaux. Ils sont rattaches a des batiments et prolonges par une dynamique horaire."

## 5. Exemple de dynamique temporelle

Sur le scenario exporte actuellement, la dynamique journaliere est lisible :

- maximum nocturne : `3 726` personnes ;
- creux diurne : `2 615` personnes vers `15 h` ;
- puis remontee en fin de journee.

Ce type de resultat montre que le modele ne reste pas statique et qu'il traduit bien un recit temporel du territoire.

Phrase utile :

"On retrouve une logique attendue : davantage de presence la nuit au domicile, une baisse en journee sous l'effet des sorties et des mobilites, puis un retour progressif le soir."

## 6. Validation et rigueur scientifique

Un point important de mon travail a ete de ne pas presenter le modele comme une verite terrain.

J'ai donc distingue :

- la coherence technique du pipeline ;
- la coherence interne du scenario ;
- la confrontation a des references externes.

J'ai aussi mis en place des validations par proxys temporels, mais je les presente comme une verification exploratoire de plausibilite, pas comme une preuve formelle.

Sur le scenario "jour ouvre hors vacances", les proxys disponibles donnent des correlations d'environ :

- `0.9721` pour les navetteurs hors commune ;
- `0.9498` pour la presence scolaire interne ;
- `0.9498` pour la charge relative des batiments d'enseignement.

Phrase utile :

"Ces validations n'ont pas valeur de preuve formelle. Elles servent seulement a verifier que certaines formes de courbe ne sont pas absurdes au regard de references documentees."

## 7. Limites du travail

Il faut etre tres clair sur ce point.

Je ne peux pas affirmer :

- que chaque personne est dans le bon batiment reel ;
- que les horaires simules sont les horaires exacts du terrain ;
- que la population non residentielle est observee parfaitement ;
- que le modele donne une photographie exacte de la commune heure par heure.

En revanche, je peux affirmer :

- que le pipeline est structure ;
- qu'il est parametre ;
- qu'il est reproductible ;
- qu'il produit des sorties exploitables ;
- qu'il integre une logique de validation et de tracabilite.

Phrase utile :

"La bonne posture scientifique est de parler d'une reconstruction plausible et argumentee, pas d'une verite observee."

## 8. Ce que j'estime avoir apporte au projet

Voici une formulation simple :

"Mon apport principal est d'avoir transforme une idee generale d'initialisation de population en un pipeline operationnel, structure par scenarios, avec des sorties exploitables dans GAMA, des outils de visualisation et un premier cadre de validation."

Tu peux aussi le dire plus directement :

- j'ai structure le pipeline ;
- j'ai relie plusieurs sources de donnees ;
- j'ai rendu le scenario parametrable ;
- j'ai produit des exports et visualisations utiles ;
- j'ai commence a formaliser la validation scientifique.

---

## Proposition de discours oral de 3 a 4 minutes

Bonjour.

Je vais vous presenter l'avancement de mon travail sur l'initialisation spatio-temporelle de la population dans le cadre du projet MOGEC, avec une application a Batz-sur-Mer.

Le probleme que j'essaie de resoudre est le suivant : a une heure donnee et dans un scenario donne, comment estimer de maniere plausible la presence de population dans les batiments du territoire ?

Pour repondre a cette question, j'ai mis en place un pipeline Python qui part de donnees ouvertes, notamment les batiments, le carroyage de population et plusieurs equipements, puis qui reconstruit une population localisee a l'echelle du batiment.

Ensuite, je ne m'arrete pas a une simple repartition residentielle. Le pipeline genere aussi des profils, des roles, des destinations et une dynamique temporelle sur 24 heures. L'objectif est donc de produire un etat initial utilisable dans GAMA, et pas seulement une carte statique.

Un point important est que le projet est scenario-dependant. Les parametres sont externalises dans des fichiers YAML, ce qui permet de faire varier l'heure, le type de jour, la saison, le contexte scolaire ou encore certains coefficients lies au tourisme ou a l'alerte.

L'export actuel correspond au scenario `xynthia_winter_night_02h`, donc une nuit d'hiver a 2 heures du matin. Sur cet export, j'obtiens 4 779 batiments modelises, dont 2 269 occupes a l'etat initial, pour une population presente de 3 726 personnes. Le modele distingue aussi plusieurs roles, par exemple 361 scolaires, 1 580 seniors, 578 actifs locaux et 919 actifs navetteurs.

La dynamique temporelle obtenue est lisible : la presence est maximale la nuit, puis elle baisse en journee jusqu'a un creux d'environ 2 615 personnes vers 15 heures, avant de remonter le soir. Cela montre que le modele restitue bien un cycle journalier plausible.

J'ai aussi cherche a encadrer scientifiquement les resultats. L'idee n'est pas de dire que le modele reproduit exactement la realite terrain, mais de distinguer ce qui repose sur des sources publiques, ce qui releve d'une hypothese de modelisation, et ce qui est seulement verifie par des tests de coherence interne. Les proxys temporels viennent en plus comme un controle faible de plausibilite, et non comme une preuve.

Donc, si je devais resumer, je dirais que mon travail a permis de construire un pipeline scenario-dependant, reproductible et exploitable, qui produit un etat initial spatio-temporel credible pour la simulation, tout en gardant une posture prudente sur la validite scientifique des resultats.

---

## Questions probables et reponses conseillees

## Questions prioritaires pour l'echange avec l'encadrante et l'equipe MOGEC

## Question : "D'ou viennent les donnees, et comment tu les lies ?"

Reponse courte :

"Le pipeline part d'un referentiel batimentaire localise sur Batz-sur-Mer, puis il y rattache plusieurs sources ouvertes. La liaison se fait soit par jointure spatiale, soit par appariement au `building_id` quand une table a deja ete preparee."

Reponse plus developpee :

- la frontiere d'etude est chargee depuis `data/01_raw/gpkg/referentiel_administratif.gpkg`, avec un buffer de lecture configurable ;
- les batiments viennent de la BD TOPO, couche `batiment` ;
- la population residente de depart vient du carroyage Filosofi 200 m ;
- les ecoles viennent du fichier `fr-en-ecoles-effectifs-nb_classes.csv`, mais sont ensuite rattachees au bati local ;
- les restaurants viennent d'un audit CSV local `data/01_raw/audit_restaurants_batz.csv`, issu d'OSM puis verifie ;
- les hebergements touristiques viennent des donnees DATAtourisme / tourisme Pays de la Loire, preparees dans `data/02_interim/external/batz_accommodation_capacity.csv` ;
- les plages viennent d'une couche geographique preparee dans `data/02_interim/external/batz_beaches.gpkg`.

Comment je les lie concretement :

- je cree d'abord un `building_id` stable pour chaque batiment ;
- pour la population residente, je fais une jointure spatiale batiment -> carreau INSEE en utilisant le centroide du batiment ;
- ensuite je ventile la population du carreau vers les batiments residentiels du carreau ;
- pour les restaurants, je cherche d'abord une intersection geometrique entre le point et le batiment, sinon je prends le batiment le plus proche dans un rayon de `80 m` ;
- pour les hebergements, je ne refais pas une jointure spatiale dans le pipeline final : je charge une table deja preparee et je la fusionne par `building_id`.

Formule precise pour la descente d'echelle residentielle :

"Dans chaque carreau Filosofi, la population est repartie entre les batiments residentiels selon un poids de capacite. La capacite vaut d'abord `nombre_de_logements` si la colonne existe, sinon elle est estimee a partir de la surface au sol et de la hauteur. Ensuite on applique un modulateur scenario-dependant sur residences principales, residences secondaires et presence a domicile."

Si on te demande "quel est l'objet central du modele ?" :

"L'objet central, c'est le batiment. Le reste du pipeline consiste a projeter des informations socio-demographiques, de destination et de temporalite sur ce referentiel batimentaire."

Formulation simple a retenir :

"Le bati est le support principal. Filosofi y apporte la population residente, les POI y apportent des destinations, et les tables preparees y apportent des capacites ou des audits."

Sources / preuves a citer :

- `config/base.yaml`
  - bloc `data_paths.input` pour les sources exactes du pipeline ;
- `src/io/loaders.py`
  - chargement de la frontiere locale et des couches spatiales ;
- `src/core/spatial_join.py`
  - jointure spatiale batiment -> carreau INSEE par centroide ;
- `src/core/downscaling.py`
  - formule de ventilation residentielle vers `pop_t0` ;
- `src/core/restaurants.py`
  - appariement restaurant -> batiment par intersection ou plus proche voisin ;
- `src/core/non_residential.py`
  - fusion des capacites d'hebergement via `building_id`.

## Question : "C'est quoi les proxies, comment tu les utilises ?"

Reponse courte :

"Un proxy, c'est une courbe de reference externe ou documentee sur 24 heures. Je l'utilise uniquement comme indicateur faible de plausibilite quand je n'ai pas de mesure terrain directe."

Reponse plus developpee :

- chaque proxy est declare dans `config/validation/proxies.yaml` ;
- un proxy contient au minimum :
  - un `metric` ;
  - parfois un `role` ou un `state` ;
  - une `reference_curve` sur 24 heures ;
  - des seuils d'acceptation ;
  - un bloc `evidence`.

Les 3 proxies actuellement utilises sont :

- `navetteurs_hors_commune_weekday`
  - metrique : `role_state_share`
  - role : `actif_navetteur`
  - etat : `exterieur`
  - interpretation : a chaque heure, quelle part des actifs navetteurs est hors commune ;
- `scolaires_presence_interne_weekday`
  - metrique : `role_internal_assigned_state_share`
  - role : `scolaire`
  - etat : `interne`
  - interpretation : parmi les scolaires affectes a une destination interne, quelle part est effectivement en presence interne selon l'heure ;
- `presence_enseignement_batiments_weekday`
  - metrique : `building_usage_count`
  - interpretation : combien de personnes sont presentes dans les batiments d'usage `Enseignement` au fil de la journee.

Ce que je compare exactement :

- la correlation entre courbe modelee et courbe de reference ;
- la RMSE ;
- la MAE ;
- le decalage entre heure de pic simulee et heure de pic de reference.

Ce que cela signifie scientifiquement :

"Un proxy n'a pas valeur de preuve. Il ne demontre ni la verite du modele, ni la justesse de la localisation des personnes. Au mieux, il signale qu'une dynamique temporelle produite n'est pas incoherente avec une courbe de reference."

Exemple concret a dire :

"Sur le scenario jour ouvre hors vacances, le proxy des navetteurs hors commune donne une correlation de `0.9721` et un ecart de pic de `0 heure`. Je peux donc dire que la forme horaire simulee ressemble a la courbe de reference choisie, mais pas que cela prouve le comportement reel des navetteurs."

Formulation simple a retenir :

"Un proxy ne prouve rien formellement ; il sert seulement a eviter des courbes manifestement aberrantes."

Sources publiques / statut a citer :

- `config/validation/proxies.yaml`
  - declaration des courbes de reference et de leurs sources ;
- `data/04_visualization/proxy_validation/proxy_validation_summary.csv`
  - resultat numerique de la comparaison ;
- statut a annoncer honnetement :
  - ce sont des comparaisons heuristiques ;
  - ce ne sont ni des preuves mathematiques, ni des validations terrain directes.

## Question : "Comment marche la matrice horaire ?"

Reponse courte :

"La matrice horaire, ce sont les colonnes `pop_h0` a `pop_h23`. Pour chaque batiment, elles donnent le nombre de personnes presentes a chaque heure."

Reponse plus developpee :

Etape 1. Generation des foyers :

- a partir de `pop_t0` dans chaque batiment, le modele reconstruit des foyers ;
- la taille des foyers suit la distribution declaree dans la configuration ;
- les roles internes sont ensuite attribues : `scolaire`, `senior`, `actif_local`, `actif_navetteur`, `inactif`.

Etape 2. Attribution d'une destination principale :

- un scolaire recoit une destination de type `Enseignement` ;
- un actif local recoit une destination interne choisie par modele gravitaire ;
- un actif navetteur recoit `EXTERIEUR` ;
- un senior ou un inactif reste par defaut a `DOMICILE`, avec ensuite des sorties ponctuelles possibles.

Etape 3. Tirage des horaires :

- pour les scolaires, actifs locaux et navetteurs, le YAML definit des distributions de depart et de retour ;
- le tirage se fait avec une loi gaussienne bornee, donc les heures varient d'un individu a l'autre ;
- exemple : un actif navetteur en semaine a un depart centre autour de `7.6 h` et un retour autour de `18.4 h` dans le scenario de base.

Etape 4. Construction de la trajectoire horaire :

- pour chaque membre, le modele fabrique une liste de 24 destinations et une liste de 24 etats ;
- les etats possibles sont `domicile`, `interne`, `exterieur` ;
- ces etats dependent de la destination principale, des sorties restaurant, des activites senior, des horaires scolaires et de certaines contraintes intra-foyer.

Etape 5. Aggregation vers les batiments :

- si la destination de l'heure est `DOMICILE`, on compte la personne dans son batiment d'origine ;
- si la destination est un `building_id` interne, on la compte dans ce batiment ;
- si la destination est `EXTERIEUR`, elle ne contribue a aucun batiment interne ;
- a la fin on remplit `pop_h0` a `pop_h23` pour chaque batiment.

Etape 6. Ajout des populations exogenes :

- certaines composantes non residentielles sont ajoutees ensuite ;
- les activites diurnes utilisent une formule surfacique de type
  `Pop_activite(t) = (surface / sqm_per_person) * (1 + client_ratio) * alpha_activite(t)` ;
- les plages, si elles sont activees, ajoutent aussi une presence horaire exogene.

Point important a dire :

"La matrice horaire n'est donc pas inventee directement a l'echelle batiment. Elle est reconstruite a partir de trajectoires individuelles simulees, puis agregée."

Formulation simple a retenir :

"La matrice horaire est une somme de presences individuelles simulees heure par heure."

Sources / preuves a citer :

- `src/core/agendas.py`
  - generation des foyers, des roles et des destinations principales ;
- `src/core/destinations.py`
  - modele gravitaire pour le choix des destinations internes ;
- `src/core/temporal.py`
  - construction des trajectoires individuelles heure par heure ;
- `config/base.yaml`
  - bloc `temporal_model.role_profiles` pour les distributions de depart et retour ;
- preuves concretes dans la config :
  - `actif_navetteur.weekday.departure.mean = 7.6`
  - `actif_navetteur.weekday.return.mean = 18.4`
  - `scolaire.weekday.attendance_probability_by_hour` pour la presence scolaire heure par heure.

## Question : "Comment on sait qui se trouve ou a quel moment ? Qu'est-ce qui est vraiment prouve ou source publiquement ?"

Reponse courte :

"On ne le sait pas par observation directe. Il faut distinguer ce qui est appuye sur une source publique, ce qui est garanti mathematiquement par le pipeline, et ce qui reste une hypothese de modelisation."

Reponse plus developpee :

Ce qu'on "sait" directement :

- la geometrie et l'usage de nombreux batiments ;
- une population agrégée par carreau via Filosofi ;
- des capacites scolaires locales ;
- des localisations de restaurants, hebergements et plages ;
- des ordres de grandeur publics comme les emplois locaux ou les parts de navette.

Ce qu'on ne sait pas directement :

- quel individu reel est dans quel batiment a `14 h 00` ;
- l'horaire exact de depart ou de retour de chaque personne ;
- l'occupation instantanee exacte de chaque batiment.

Donc la logique du modele est la suivante :

- j'ancre le modele sur des donnees observees ou ouvertes ;
- j'ajoute des regles explicites pour completer ce qui n'est pas observe ;
- j'enregistre ces regles dans la configuration ;
- puis je confronte le resultat a des references externes quand c'est possible.

Ce que je peux vraiment soutenir separement :

1. Les sources publiques ou verifiables
- BD TOPO pour le bati ;
- Filosofi pour la population residente agrégée ;
- fichiers locaux ou open data pour les ecoles, restaurants, hebergements, plages.

2. Les garanties mathematiques internes du pipeline
- la population d'un carreau est redistribuee vers les batiments sans perte arbitraire d'unites grace a la methode du plus fort reste ;
- les colonnes horaires `pop_h0` a `pop_h23` sont reconstruites par aggregation explicite des trajectoires ;
- les cibles globales de roles peuvent etre imposees exactement par reequilibrage ;
- le pipeline est reproductible a graine aleatoire fixee.

3. Les hypotheses de modelisation, qui ne sont pas prouvees
- la formule d'hebergement touristique ;
- la formule d'activite diurne ;
- les distributions horaires de depart et de retour ;
- le choix d'une destination interne par modele gravitaire ;
- les proxies temporels.

4. Les controles externes, de valeur variable
- comparaison a des ordres de grandeur publics ;
- confrontation a quelques horaires publics ;
- proxies temporels, qui ont une valeur faible et indicative ;
- eventuellement, plus tard, observations de terrain ou expertise locale, qui auraient une valeur plus forte.

La formulation la plus juste est :

"Je ne sais pas ou se trouve chaque personne reelle. Ce que je peux defendre, c'est qu'on genere des individus synthetiques a partir de sources publiques, avec quelques garanties mathematiques internes, puis avec des hypotheses explicites dont le statut reste modelise et non prouve."

Si on te demande "mais alors, pourquoi vous dites que telle personne est la ?" :

"On ne parle pas d'une personne reelle observee. On parle d'un agent synthetique genere par le modele, dont la position resulte d'un ensemble d'hypotheses parametrees et tracables."

Formulation tres importante a retenir :

"Je ne pretends pas localiser les personnes reelles. Je produis une population synthetique localisee, scenario-dependante, appuyee sur des donnees reelles et des hypotheses explicites."

Sources publiques / garanties mathematiques / hypotheses a citer :

- Sources publiques fortes :
  - BD TOPO ;
  - Filosofi ;
  - Insee emplois / capacites touristiques ;
  - horaires publics des ecoles ;
  - couches geographiques locales.
- Garanties mathematiques internes :
  - ventilation residentielle avec conservation des effectifs par arrondi controle ;
  - aggregation explicite des trajectoires en `pop_h0` a `pop_h23` ;
  - reproductibilite avec `random_seed` fixe.
- Hypotheses non prouvees :
  - `Pop_hebergement = Capacite_lits * tau_occupation * alpha_tourist_t0` ;
  - `Pop_activite(t) = (surface / sqm_per_person) * (1 + client_ratio) * alpha_activite(t)` ;
  - toutes les courbes proxy.

Phrase tres utile si on te demande "ou sont les preuves ?" :

"Il n'y a pas de preuve formelle que le modele localise correctement les personnes reelles. Ce qu'il y a, ce sont des sources publiques solides pour certaines entrees, des garanties mathematiques sur certains calculs internes, et des hypotheses explicites pour tout le reste."

## Question : "En une phrase, ton travail sert a quoi ?"

Reponse courte :

"Il sert a generer un etat initial spatio-temporel plausible de la population, utilisable dans GAMA pour les simulations MOGEC."

## Question : "Quelle est ta principale contribution ?"

Reponse :

"Ma principale contribution est d'avoir construit et structure un pipeline complet qui relie les donnees spatiales, la generation de population, les scenarios temporels et l'export vers GAMA, avec en plus des outils de validation."

## Question : "Pourquoi Batz-sur-Mer ?"

Reponse :

"Parce que c'est le terrain d'etude mobilise dans le cadre MOGEC, notamment pour des scenarios de submersion, et que cela fournit un cas concret pour concevoir puis tester le pipeline."

## Question : "Pourquoi parler de scenario ?"

Reponse :

"Parce que la population presente depend fortement du contexte. Une nuit d'hiver, une journee de vacances ou un jour ouvre hors vacances ne donnent pas la meme repartition. Le pipeline doit donc produire des etats initiaux dependants du contexte."

## Question : "Comment repartis-tu la population dans les batiments ?"

Reponse :

"Je pars d'un carroyage de population, que je joins aux batiments. Ensuite, la population residentielle est ventilee vers les batiments selon des regles definies dans le pipeline, puis enrichie par d'autres composantes et par les profils d'agents."

Si on te pousse davantage :

"L'idee est de passer d'une information agregee sur une maille spatiale a une affectation plus fine a l'echelle du batiment, tout en gardant des regles explicites et reproductibles."

## Question : "Comment generes-tu la dynamique sur 24 heures ?"

Reponse :

"Le modele attribue des roles et des agendas a des agents ou membres de foyers, puis traduit leurs deplacements et presences en population presente par batiment heure par heure."

## Question : "Comment sais-tu que le resultat est bon ?"

Reponse prudente :

"Je ne dirais pas qu'il est 'prouve'. Je dirais qu'il est partiellement contraint par des sources publiques, rigoureux sur certains calculs internes, et encore hypothétique sur plusieurs briques de comportement."

## Question : "Quelles sont les limites actuelles ?"

Reponse :

"La principale limite est qu'on reste sur une reconstruction modelisee. On ne dispose pas d'une observation exhaustive de la population reelle heure par heure et batiment par batiment. Donc il faut rester prudent sur l'interpretation et continuer la confrontation a des references externes."

## Question : "Qu'est-ce qui est robuste aujourd'hui ?"

Reponse :

"La structure du pipeline, le caractere parametrable des scenarios, la reproductibilite des sorties, la tracabilite d'une partie des hypotheses et l'existence de premiers outils de validation."

## Question : "Qu'est-ce qu'il reste a ameliorer ?"

Reponse :

"Il reste surtout a approfondir la validation externe, a mieux documenter certaines hypotheses sensibles et a continuer les tests sur des scenarios contrasts pour verifier la stabilite du modele."

## Question : "En quoi ton travail aide le reste de l'equipe ?"

Reponse :

"Il fournit une base d'initialisation plus exploitable pour la simulation, mais aussi des sorties plus lisibles, des scenarios parametrables et un cadre de discussion plus clair sur la validite des hypotheses."

## Question : "Est-ce que ton modele montre la population reelle ?"

Reponse a utiliser telle quelle :

"Non. Il produit une reconstruction plausible et argumentee de la population presente, utile pour la simulation, mais il ne faut pas le presenter comme une observation directe de la realite."

## Question : "Pourquoi tes validations sont-elles des proxys et pas une validation directe ?"

Reponse :

"Parce qu'on ne dispose pas de verite terrain complete a l'echelle batimentaire et horaire. Mais je precise aussi que les proxys ont une portee limitee : ils sont utiles pour eliminer des dynamiques absurdes, pas pour prouver scientifiquement le modele."

## Question : "Si on te demande ta conclusion en 20 secondes ?"

Reponse :

"J'ai construit un pipeline scenario-dependant qui genere une population localisee et dynamique pour Batz-sur-Mer, exploitable dans GAMA, avec une logique de validation et de tracabilite, tout en gardant une posture prudente sur la veracite terrain."

---

## Questions que tu peux poser toi-meme en fin de presentation

Si tu veux finir de maniere mature et ouverte :

- "Je serais preneur d'un retour sur le niveau de prudence scientifique a adopter dans la formulation des resultats."
- "Je voudrais aussi savoir si vous jugez prioritaire d'approfondir la validation externe ou plutot d'etendre encore les scenarios."
- "Je peux egalement avoir votre avis sur ce qui serait le plus utile pour l'integration aval dans GAMA."

---

## Conseils de posture pour demain

- Parle lentement.
- Ne cherche pas a tout dire.
- Insiste sur la logique generale avant les details.
- N'essaie pas de survendre les resultats.
- Utilise souvent les mots "plausible", "parametre", "tracable", "scenario".
- Si tu ne sais pas repondre a une question, dis :
  "Je n'ai pas encore stabilise ce point, mais c'est justement une limite ou une piste de travail que j'ai identifiee."

---

## Resume ultra-court a memoriser

"J'ai developpe un pipeline qui produit, a partir de donnees spatiales et de parametres de scenario, une reconstruction plausible de la population presente dans les batiments de Batz-sur-Mer au cours de la journee. Le resultat est exploitable dans GAMA, accompagne d'outils de visualisation et d'un premier cadre de validation."
