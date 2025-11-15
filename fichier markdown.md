# **Documentation Technique du Projet**

## **Planificateur de Menus Hebdomadaire (Gemini-Powered)**

**Auteur :** Gemini

**Date :** 2025-11-15

## **1\. Introduction au Projet**

Le Planificateur de Menus Hebdomadaire est une solution automatisée conçue pour générer des plans de repas personnalisés en se basant sur l'inventaire d'ingrédients disponibles par l'utilisateur. Le cœur du système repose sur l'API Google Gemini, qui est utilisée à la fois pour la catégorisation intelligente des ingrédients et pour la génération finale du menu.

### **Objectifs Clés**

* Maximiser l'utilisation des ingrédients déjà disponibles pour minimiser le gaspillage et les achats.  
* Générer un plan de repas équilibré et varié pour une période donnée.  
* Simplifier la gestion de l'inventaire grâce à une interface utilisateur conviviale et une catégorisation assistée par IA.  
* Fournir des outils pour l'expansion facile de la base de données de recettes.

## **2\. Architecture et Composants du Système**

Le projet est divisé en trois zones principales : la gestion des données de recettes, la gestion de l'inventaire utilisateur, et le moteur de planification.

### **Base de Données de Recettes**

La source unique de toutes les recettes est un fichier CSV structuré.

* recettes \- reprends la premiere table que tu as fournie. DOn....csv  
  C'est la base de données maîtresse. Elle contient les champs essentiels requis pour la planification : Title, Key Ingredients, Prep Time (min), Cook Time (min), Contains meat/fish?, et URL.

### **Composants d'Inventaire et de Sélection**

Ce module gère l'interface utilisateur pour la sélection des ingrédients et le stockage des données.

* streamlit\_ingredient\_selector.py  
  L'application Streamlit principale pour l'inventaire. Elle extrait les ingrédients de la base de données, utilise l'IA pour les classer, et permet à l'utilisateur de cocher ceux qu'il possède.  
* files/all\_categorized\_ingredients\_cache.json  
  Fichier cache stockant le résultat de la première catégorisation d'ingrédients effectuée par Gemini. Il évite des appels API répétés.  
* files/categorized\_available\_ingredients.json  
  Le fichier de sortie principal. Il stocke les ingrédients que l'utilisateur a sélectionnés, sous forme structurée (catégories $\\rightarrow$ liste d'ingrédients). Ce fichier est l'entrée essentielle pour le module de planification.  
* export\_selected\_ingredients\_csv.py  
  Script utilitaire pour exporter la sélection catégorisée vers un format CSV simple, si nécessaire.

### **Moteur de Planification (Core Intelligence)**

Ce script consomme l'inventaire et génère le plan de repas final en utilisant le raisonnement de l'IA.

* generateur\_menu\_gemini.py  
  Le script cœur. Il charge les recettes et l'inventaire, calcule le nombre d'ingrédients manquants pour chaque recette, et utilise l'API Gemini pour construire un menu cohérent de $N$-jours en priorisant les recettes à faible score de manquant.  
* meal\_plan.md  
  Le fichier de sortie généré par le planificateur, contenant le menu sous forme de tableau Markdown.

## **3\. Configuration et Prérequis**

### **Prérequis Logiciels**

Le projet est basé sur Python et nécessite les bibliothèques suivantes :

pip install streamlit pandas requests

### **Configuration de l'API Gemini**

L'utilisation de l'IA (pour la catégorisation et la planification) nécessite une clé API.

Étape 1 : Obtenir la clé  
Vous devez obtenir une clé d'API valide pour le modèle Gemini.  
Étape 2 : Configuration de l'environnement  
La clé doit être définie comme une variable d'environnement pour être lue par les scripts Python.  
export GEMINI\_API\_KEY="VOTRE\_CLÉ\_API\_ICI"

**Note :** Tous les appels API utilisent le modèle **gemini-2.5-flash-preview-09-2025**.

## **4\. Guide d'Utilisation du Flux de Travail**

Le processus de génération du menu se déroule en deux étapes principales et séquentielles.

### **Étape 1 : Sélectionner l'Inventaire des Ingrédients**

Cette étape crée le fichier d'inventaire requis par le planificateur.

1. **Lancement de l'application Streamlit :** Exécutez le script de sélection :  
   streamlit run streamlit\_ingredient\_selector.py

2. **Catégorisation IA :** Lors de la première exécution, l'application appellera Gemini pour catégoriser tous les ingrédients uniques des recettes. Les résultats sont cachés dans files/all\_categorized\_ingredients\_cache.json.  
3. **Sélection :** Utilisez les cases à cocher, organisées par catégories (e.g., Légumes, Produits Laitiers), pour indiquer les ingrédients dont vous disposez.  
4. **Sauvegarde :** Cliquez sur le bouton **Save Inventory** (Enregistrer l'Inventaire). Cela génère le fichier essentiel files/categorized\_available\_ingredients.json.

### **Étape 2 : Générer le Plan de Repas**

Une fois l'inventaire sauvegardé, le planificateur peut être lancé.

1. **Lancement du Script Python :** Exécutez le script de planification :  
   python generateur\_menu\_gemini.py

2. **Paramètres :** Utilisez le curseur pour choisir le nombre de jours à planifier (par défaut 5 jours).  
3. **Génération IA :** Cliquez sur le bouton **Generate Menu with Gemini** (Générer le Menu avec Gemini).  
4. **Traitement :** Le script charge l'inventaire et les recettes, calcule les scores de manquant, et envoie le tout à Gemini avec un prompt très précis pour générer le tableau de menu.  
5. **Affichage et Sauvegarde :** Le plan de repas final, formaté en Markdown, est affiché et sauvegardé sous **meal\_plan.md** (dans le même répertoire que le script).

## **5\. Gestion et Expansion des Recettes**

Deux scripts utilitaires permettent d'ajouter de nouvelles recettes à la base de données (recettes \- reprends la premiere table que tu as fournie. DOn....csv).

### **Ajout de Recette par URL (Assisté par IA)**

Le script **add\_recipe\_from\_url.py** utilise Gemini pour extraire automatiquement les informations structurées à partir d'une URL de recette, garantissant que les nouvelles entrées respectent le format de la base de données (colonnes requises, temps en minutes, statut Oui/Non).

1. **Lancement :**  
   python add\_recipe\_from\_url.py

2. **Saisie :** Entrez l'URL lorsque vous y êtes invité.  
3. **Traitement IA :** Gemini analyse l'URL et renvoie les détails au format JSON, qui sont ensuite mappés aux colonnes du CSV et ajoutés à la fin du fichier maître.

### **Ajout de Recette Manuel**

Le script **add\_recipe\_manually.py** fournit une interface en ligne de commande pour saisir manuellement les détails d'une recette, avec validation des types de données (entiers pour les temps, Oui/Non pour le statut viande/poisson).

1. **Lancement :**  
   python add\_recipe\_manually.py

2. **Saisie Guidée :** Le script vous guide à travers chaque champ (**Title**, **Key Ingredients**, **Prep Time (min)**, etc.).  
3. **Validation :** Le script s'assure que les entrées sont du bon type avant l'enregistrement.  
4. **Sauvegarde :** Les données sont ajoutées à la fin du fichier CSV maître après confirmation.