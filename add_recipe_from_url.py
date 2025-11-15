import csv
import json
import requests
import os
import sys
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
RECIPE_FILE_PATH = "files/recipes.csv"
URL_RECIPE_FILE_PATH = "files/URL_recipes.csv"
AVAILABLE_INGREDIENTS_CSV = "files/available_ingredients.csv" 


# Clé API Gemini. Laissez ceci comme `os.environ.get('GEMINI_API_KEY')` 
# pour que l'environnement de la plateforme la fournisse automatiquement.
API_KEY = GOOGLE_API_KEY
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key="

# Schéma JSON pour forcer la structure de la recette extraite par l'IA.
# Cela garantit le respect des colonnes et des règles de formatage.
RECIPE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "Titre": {"type": "STRING", "description": "Titre exact de la recette."},
        "Ingredients_Cles": {"type": "STRING", "description": "Liste courte et condensée des 3 à 5 ingrédients principaux."},
        "Preparation_min": {"type": "INTEGER", "description": "Temps de préparation arrondi à l'entier le plus proche (en minutes)."},
        "Cuisson_min": {"type": "INTEGER", "description": "Temps de cuisson arrondi à l'entier le plus proche (en minutes)."},
        "Contient_viande_poisson": {"type": "STRING", "description": "Réponse 'Oui' ou 'Non' uniquement."},
        "URL": {"type": "STRING", "description": "L'URL fournie par l'utilisateur."}
    },
    # Les clés requises correspondent aux noms de colonnes du fichier CSV après mappage
    "required": ["Titre", "Ingredients_Cles", "Preparation_min", "Cuisson_min", "Contient_viande_poisson", "URL"]
}

def extract_recipe_details(recipe_url):
    """
    Appelle l'API Gemini pour extraire les détails d'une recette à partir de son URL.
    
    NOTE: La recherche Google (grounding) est désactivée car elle n'est pas compatible
    avec la réponse structurée JSON. Nous nous fions ici à la capacité du modèle
    à analyser l'URL fournie dans le prompt.
    """
    if not API_KEY and not API_URL.endswith("key="):
        print("Avertissement: La clé API est manquante. Impossible de se connecter à Gemini.")
        return None

    system_prompt = (
        "Vous êtes un extracteur de données de recettes. Votre tâche est d'analyser l'URL fournie "
        "par l'utilisateur, d'extraire le titre, les ingrédients clés, les temps de préparation et de cuisson, "
        "et de déterminer si la recette contient de la viande ou du poisson. "
        "Le temps doit être un nombre entier (en minutes). La colonne 'Contient viande/poisson ?' doit être 'Oui' ou 'Non'. "
        "Vous devez répondre STRICTEMENT au format JSON en respectant le schéma fourni."
    )
    
    # La requête de l'utilisateur inclut l'URL pour guider la recherche Google
    # Nous incluons également l'URL dans la structure JSON de sortie souhaitée.
    user_query = f"""
    Extraire les détails de la recette trouvée à l'URL suivante : {recipe_url}
    Une fois les informations extraites, incluez l'URL d'origine dans la clé 'URL' de votre réponse JSON.
    """
    
    payload = {
        "contents": [
            {"parts": [{"text": user_query}]}
        ],
        # LE BLOC 'tools' QUI CAUSAIT L'ERREUR 400 EST RETIRÉ ICI.
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RECIPE_SCHEMA
        }
    }

    headers = {
        'Content-Type': 'application/json'
    }

    print(f"-> Recherche des détails de la recette pour l'URL: {recipe_url}...")
    try:
        # Construction de l'URL finale pour l'appel
        final_api_url = API_URL + API_KEY
        response = requests.post(final_api_url, headers=headers, data=json.dumps(payload), timeout=60)
        
        if response.status_code == 200:
            response_data = response.json()
            
            # Vérification de la structure de la réponse avant l'extraction
            if 'candidates' not in response_data or not response_data['candidates']:
                print("Erreur: L'API Gemini n'a pas retourné de candidat valide.")
                return None
            
            # Extraire et parser le JSON
            json_text = response_data['candidates'][0]['content']['parts'][0]['text']
            recipe_data = json.loads(json_text)
            
            # Mappage des clés JSON (snake_case) aux noms de colonnes du CSV
            mapped_data = {
                'Titre': recipe_data['Titre'],
                'Ingrédients Clés': recipe_data['Ingredients_Cles'],
                'Préparation (min)': recipe_data['Preparation_min'],
                'Cuisson (min)': recipe_data['Cuisson_min'],
                'Contient viande/poisson ?': recipe_data['Contient_viande_poisson'],
                'URL': recipe_data['URL']
            }
            return mapped_data
        else:
            print(f"Erreur de l'API Gemini (Code: {response.status_code}).")
            print("Veuillez vérifier votre clé API ou si l'API est accessible.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Erreur de connexion à l'API: {e}")
        return None
    except json.JSONDecodeError:
        print("Erreur: L'API n'a pas retourné un JSON valide. La structure de la recette n'a pas pu être extraite.")
        return None
    except Exception as e:
        print(f"Une erreur inattendue s'est produite: {e}")
        return None


def append_recipe_to_csv(recipe_data, filepath):
    """Ajoute une ligne de données de recette au fichier CSV existant."""
    if not recipe_data:
        print("Aucune donnée de recette valide à ajouter.")
        return

    # Définition de l'ordre des colonnes, basé sur votre fichier
    fieldnames = ['Titre', 'Ingrédients Clés', 'Préparation (min)', 'Cuisson (min)', 'Contient viande/poisson ?', 'URL']
    
    try:
        # 1. Vérifiez si le fichier existe et s'il se termine par un saut de ligne
        file_needs_newline = False
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                # Aller à la fin du fichier et lire le dernier caractère
                try:
                    f.seek(-1, os.SEEK_END)
                    last_char = f.read(1)
                    # Vérifier si le dernier caractère n'est PAS un saut de ligne
                    if last_char not in (b'\n', b'\r'):
                        file_needs_newline = True
                except OSError:
                    # Le fichier est vide, donc pas besoin d'ajouter de saut de ligne
                    pass

        # 2. Ouvrez le fichier en mode ajout ('a') avec newline=''
        with open(filepath, mode='a', encoding='utf-8', newline='') as csvfile:
            
            # Si un saut de ligne est nécessaire, ajoutez-le manuellement
            if file_needs_newline:
                csvfile.write('\n')

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            # Les données de la recette sont ajoutées en ligne
            writer.writerow(recipe_data)

        print(f"\n✅ Succès : La recette '{recipe_data['Titre']}' a été ajoutée à '{filepath}'.")

    except FileNotFoundError:
        print(f"Erreur: Le fichier cible '{filepath}' n'a pas été trouvé. Veuillez vérifier le chemin.")
    except UnicodeEncodeError:
        print("Erreur d'encodage: Impossible d'écrire certains caractères. Assurez-vous que l'encodage UTF-8 est supporté.")
    except Exception as e:
        print(f"Erreur lors de l'écriture du fichier CSV: {e}")


def append_url_to_csv(recipe_data, filepath):
    """Ajoute une ligne de données de recette au fichier CSV existant."""
    if not recipe_data:
        print("Aucune donnée de recette valide à ajouter.")
        return
    # Définition de l'ordre des colonnes, basé sur votre fichier
    fieldnames = ['URL']

    try:
        # 1. Vérifiez si le fichier existe et s'il se termine par un saut de ligne
        file_needs_newline = False
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                # Aller à la fin du fichier et lire le dernier caractère
                try:
                    f.seek(-1, os.SEEK_END)
                    last_char = f.read(1)
                    # Vérifier si le dernier caractère n'est PAS un saut de ligne
                    if last_char not in (b'\n', b'\r'):
                        file_needs_newline = True
                except OSError:
                    # Le fichier est vide, donc pas besoin d'ajouter de saut de ligne
                    pass

        # 2. Ouvrez le fichier en mode ajout ('a') avec newline=''
        with open(filepath, mode='a', encoding='utf-8', newline='') as csvfile:
            
            # Si un saut de ligne est nécessaire, ajoutez-le manuellement
            if file_needs_newline:
                csvfile.write('\n')
          
            writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            # Les données de la recette sont ajoutées en ligne
            writer.writerow([recipe_data])

        print(f"\n✅ Succès : URL '{recipe_data}' a été ajoutée à '{filepath}'.")
        print(recipe_data)

    except FileNotFoundError:
        print(f"Erreur: Le fichier cible '{filepath}' n'a pas été trouvé. Veuillez vérifier le chemin.")
    except UnicodeEncodeError:
        print("Erreur d'encodage: Impossible d'écrire certains caractères. Assurez-vous que l'encodage UTF-8 est supporté.")
    except Exception as e:
        print(f"Erreur lors de l'écriture du fichier CSV: {e}")
    

    



def main():
    """Fonction principale pour orchestrer l'extraction et l'ajout."""
    
    # Vérification que le fichier existe
    if not os.path.exists(RECIPE_FILE_PATH):
        print(f"Erreur: Le fichier des recettes '{RECIPE_FILE_PATH}' n'existe pas.")
        print("Veuillez vous assurer qu'il est bien présent avant d'exécuter le script.")
        # Utiliser sys.exit pour sortir proprement si le fichier est manquant
        sys.exit(1)

    print("--- Ajout de Recette par URL (via Gemini API) ---")
    
    # Demander l'URL à l'utilisateur
    #recipe_url = input("Veuillez entrer l'URL de la recette à ajouter : ").strip()
    recipe_url = 'https://jow.fr/recipes/poulet-fondue-de-poireaux-et-penne-8xd00zbzg4k0037m1cus'

    if not recipe_url:
        print("Opération annulée: Aucune URL fournie.")
        return

    # 1. Extraction des détails via Gemini
    new_recipe_details = extract_recipe_details(recipe_url)
    
    if new_recipe_details:
        # 2. Ajout de la nouvelle ligne au fichier CSV
        append_recipe_to_csv(new_recipe_details, RECIPE_FILE_PATH)
        append_url_to_csv(recipe_url, URL_RECIPE_FILE_PATH)
    else:
        print("\n❌ Échec de l'extraction des détails de la recette. La ligne n'a pas été ajoutée.")


if __name__ == "__main__":
    main()