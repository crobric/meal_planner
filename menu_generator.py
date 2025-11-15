import csv
import json
import requests
import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
RECIPE_FILE_PATH = "files/recipes.csv"
URL_RECIPE_FILE_PATH = "files/URL_recipes.csv"
AVAILABLE_INGREDIENTS_CSV = "files/available_ingredients.csv" 

weekly_recipes_json = "files/weekly_recipes.json"
shopping_list_json = "files/shopping_list.json"

# IMPORTANT : Vous devez définir votre clé API Gemini.
# Vous pouvez l'obtenir sur https://aistudio.google.com/
# Ne partagez jamais cette clé publiquement.
API_KEY = GOOGLE_API_KEY # ou mettez-la en dur : "VOTRE_CLE_API_ICI"

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={API_KEY}"
# ---------------------

#Recover available ingredients from CSV file
with open(AVAILABLE_INGREDIENTS_CSV, 'r', newline='', encoding='utf-8') as csvfile:
    reader = csv.reader(csvfile)
    ligne = next(reader)
    available_ingredients = ','.join(ligne)
 

def load_recipes_from_csv(filepath):
    """Charge les recettes depuis le fichier CSV et les retourne en liste de dictionnaires."""
    recipes = []
    try:
        with open(filepath, mode='r', encoding='utf-8') as f:
            # Gère les guillemets qui peuvent entourer les champs
            reader = csv.DictReader(f, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True)
            for row in reader:
                recipes.append(row)
        if not recipes:
            print(f"Erreur: Le fichier CSV '{filepath}' est vide ou n'a pas pu être lu.")
            return None
        return recipes
    except FileNotFoundError:
        print(f"Erreur: Le fichier '{filepath}' n'a pas été trouvé.")
        print("Veuillez vous assurer que le nom du fichier est correct et qu'il se trouve dans le même dossier que le script.")
        return None
    except Exception as e:
        print(f"Erreur inattendue lors de la lecture du CSV: {e}")
        return None

def generate_meal_plan(recipes_json_string, available_ingredients):
    """Appelle l'API Gemini pour générer un plan de repas et une liste de courses."""
    
    if not API_KEY or API_KEY == "VOTRE_CLE_API_ICI":
        print("Erreur: La clé API GEMINI_API_KEY n'est pas configurée.")
        print("Veuillez définir la variable d'environnement GEMINI_API_KEY ou la modifier dans le script.")
        return None

    system_prompt = (
        "Tu es un assistant expert en planification de repas. "
        "Tu crées un plan de repas pour 7 jours (midi et soir) et une liste de courses. "
        "Tu te bases sur une liste de recettes fournie en JSON et des contraintes spécifiques. "
        "Tu réponds TOUJOURS au format JSON en respectant le schéma demandé."
    )

    user_prompt = f"""
    Voici la liste complète des recettes disponibles au format JSON :
    {recipes_json_string}

    Veuillez maintenant générer un plan de repas en respectant IMPÉRATIVEMENT les contraintes suivantes :
    1.  **Ingrédients disponibles :** J'ai déjà {available_ingredients}. Vous devez prioriser les recettes qui utilisent ces ingrédients.
    2.  **Règle du soir :** Les repas du soir (Lundi Soir, Mardi Soir, etc.) ne doivent **jamais** contenir de viande ou de poisson. Utilisez uniquement les recettes où "Contient viande/poisson ?" est "Non".
    3.  **Règle du midi :** Les repas du midi peuvent contenir de la viande ou du poisson ("Oui" ou "Non").
    4.  **Variété :** Essayez de ne pas répéter les mêmes plats.
    5.  **Liste de courses :** Générez une liste de courses catégorisée pour tous les ingrédients nécessaires pour ce plan, *sauf* ceux que j'ai déjà (listés au point 1).

    Générez le plan complet et la liste de courses.
    """
    print(user_prompt)
    # Schéma JSON pour forcer la sortie structurée de Gemini
    json_schema = {
        "type": "OBJECT",
        "properties": {
            "plan_repas": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "jour": {"type": "STRING"},
                        "midi": {
                            "type": "OBJECT",
                            "properties": {
                                "titre": {"type": "STRING"},
                                "url": {"type": "STRING"}
                            },
                            "required": ["titre", "url"]
                        },
                        "soir": {
                            "type": "OBJECT",
                            "properties": {
                                "titre": {"type": "STRING"},
                                "url": {"type": "STRING"}
                            },
                             "required": ["titre", "url"]
                        }
                    },
                    "required": ["jour", "midi", "soir"]
                }
            },
            "liste_courses": {
                "type": "OBJECT",
                "properties": {
                    "viande_poisson": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "laitiers_frais": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "legumes_feculents": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "epicerie": {"type": "ARRAY", "items": {"type": "STRING"}}
                },
                "required": ["viande_poisson", "laitiers_frais", "legumes_feculents", "epicerie"]
            }
        },
        "required": ["plan_repas", "liste_courses"]
    }

    payload = {
        "contents": [
            {"parts": [{"text": user_prompt}]}
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": json_schema,
            "temperature": 0.7 # Un peu de créativité pour le planning
        }
    }

    headers = {
        'Content-Type': 'application/json'
    }

    print("Envoi de la requête à l'API Gemini... (cela peut prendre quelques secondes)")
    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=60)
        
        if response.status_code == 200:
            response_data = response.json()
            # Extraire le texte JSON de la réponse de l'API
            json_text = response_data['candidates'][0]['content']['parts'][0]['text']
            # Le parser en tant qu'objet Python
            return json.loads(json_text)
        else:
            print(f"Erreur de l'API Gemini (Code: {response.status_code}):")
            print(response.text)
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Erreur de connexion à l'API: {e}")
        return None
    except (KeyError, IndexError):
        print("Erreur: La réponse de l'API n'a pas le format attendu.")
        print(response.json())
        return None
    except json.JSONDecodeError:
        print("Erreur: L'API n'a pas retourné un JSON valide.")
        print(response_data)
        return None


def print_results(data):
    """Affiche le plan de repas et la liste de courses de manière formatée."""
    
    print("\n" + "="*40)
    print("🗓️ VOTRE PLAN DE REPAS OPTIMISÉ 🗓️")
    print("="*40)

    plan = data.get('plan_repas', [])
    for day in plan:
        print(f"\n--- {day['jour'].upper()} ---")
        print(f"  Midi: {day['midi']['titre']}")
        print(f"        ( {day['midi']['url']} )")
        print(f"  Soir: {day['soir']['titre']} (Végétarien)")
        print(f"        ( {day['soir']['url']} )")

    print("\n" + "="*40)
    print("🛒 VOTRE LISTE DE COURSES 🛒")
    print("="*40)
    print(f"(N'oubliez pas, {available_ingredients} ne sont pas listés)")

    with open(weekly_recipes_json, mode='w', encoding='utf-8') as f:
        # Utiliser indent=4 pour une meilleure lisibilité du fichier JSON sauvegardé
        json.dump(plan, f, indent=4, ensure_ascii=False)

    shopping_list = data.get('liste_courses', {})
    for category, items in shopping_list.items():
        if items: # N'affiche que les catégories non vides
            print(f"\n[{category.replace('_', ' ').capitalize()}]:")
            for item in items:
                print(f"  - {item}")

    """Sauvegarde de la liste de catégorisées dans un fichier JSON."""
    # Assurez-vous que le répertoire 'files/' existe
    os.makedirs(os.path.dirname(shopping_list_json), exist_ok=True)
    
    with open(shopping_list_json, mode='w', encoding='utf-8') as f:
        # Utiliser indent=4 pour une meilleure lisibilité du fichier JSON sauvegardé
        json.dump(shopping_list, f, indent=4, ensure_ascii=False)



def main():
    """Fonction principale du script."""
    print("Chargement des recettes depuis le fichier CSV...")
    recipes_list = load_recipes_from_csv(RECIPE_FILE_PATH)
    
    if recipes_list:
        # Convertit la liste en chaîne JSON pour l'envoyer à l'API
        recipes_json_string = json.dumps(recipes_list, indent=2, ensure_ascii=False)
        
        # Génère le plan
        generated_data = generate_meal_plan(recipes_json_string, available_ingredients)
        
        if generated_data:
            # Affiche les résultats
            print_results(generated_data)

if __name__ == "__main__":
    main()