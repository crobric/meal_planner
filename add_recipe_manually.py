import csv
import os
import sys
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
RECIPE_FILE_PATH = "files/recipes.csv"
URL_RECIPE_FILE_PATH = "files/URL_recipes.csv"
AVAILABLE_INGREDIENTS_CSV = "files/available_ingredients.csv" 

# Définition des champs requis et leur type pour la validation.
FIELD_DEFINITIONS = [
    {'name': 'Titre', 'prompt': 'Titre de la recette : '},
    {'name': 'Ingrédients Clés', 'prompt': 'Ingrédients clés (ex: poulet, riz, brocoli) : '},
    {'name': 'Préparation (min)', 'prompt': 'Temps de préparation (en minutes, nombre entier) : ', 'type': 'int'},
    {'name': 'Cuisson (min)', 'prompt': 'Temps de cuisson (en minutes, nombre entier) : ', 'type': 'int'},
    {'name': 'Contient viande/poisson ?', 'prompt': 'Contient de la viande ou du poisson ? (Oui/Non) : ', 'type': 'yes_no'},
]
# Le champ 'URL' est géré séparément car il est facultatif.
FIELD_URL = {'name': 'URL', 'prompt': 'URL de la recette (facultatif, laissez vide si non applicable) : '}


def get_validated_input(field_def):
    """
    Demande une entrée à l'utilisateur et la valide selon le type défini.
    Retourne la valeur validée ou renvoie un message d'erreur si l'entrée est invalide.
    """
    prompt = field_def['prompt']
    field_type = field_def.get('type')
    value = None

    while value is None:
        user_input = input(prompt).strip()
        
        # Gestion des champs facultatifs (ici, l'URL est gérée dans la fonction principale)
        if not user_input and field_type is None:
            return user_input # Accepte une chaîne vide pour les champs texte
        
        if field_type == 'int':
            try:
                # Tente de convertir en entier. Doit être >= 0
                int_val = int(user_input)
                if int_val >= 0:
                    value = int_val
                else:
                    print("⚠️ Le temps doit être un nombre entier positif ou nul.")
            except ValueError:
                print("⚠️ Veuillez entrer un nombre entier valide pour le temps.")

        elif field_type == 'yes_no':
            if user_input.lower() in ['oui', 'non', 'yes', 'no']:
                # Standardise en 'Oui' ou 'Non'
                value = 'Oui' if user_input.lower() in ['oui', 'yes'] else 'Non'
            else:
                print("⚠️ Réponse invalide. Veuillez répondre par 'Oui' ou 'Non'.")

        elif field_type is None: # Champs de type texte (Titre, Ingrédients Clés)
            if user_input:
                value = user_input
            else:
                print(f"⚠️ {field_def['name']} ne peut pas être vide.")

    return value


def collect_recipe_data():
    """Collecte toutes les données de la recette auprès de l'utilisateur."""
    print("\n--- Saisie Manuelle de la Recette ---")
    recipe_data = {}
    
    # 1. Collecte des champs obligatoires et validation
    for field_def in FIELD_DEFINITIONS:
        recipe_data[field_def['name']] = get_validated_input(field_def)
        
    # 2. Collecte du champ facultatif (URL)
    recipe_data[FIELD_URL['name']] = input(FIELD_URL['prompt']).strip()
    
    # 3. Affichage pour confirmation
    print("\n--- Récapitulatif de la Recette ---")
    for key, value in recipe_data.items():
        print(f"{key}: {value}")
    
    confirm = input("\nConfirmez-vous l'ajout de cette recette ? (o/n) : ").strip().lower()
    if confirm == 'o':
        return recipe_data
    else:
        print("Ajout annulé par l'utilisateur.")
        return None


def append_to_csv(recipe_data, filepath):
    """Ajoute une ligne de données de recette au fichier CSV existant."""
    if not recipe_data:
        print("Aucune donnée de recette valide à ajouter.")
        return

    # Définition de l'ordre des colonnes (doit correspondre au fichier existant)
    fieldnames = ['Titre', 'Ingrédients Clés', 'Préparation (min)', 'Cuisson (min)', 'Contient viande/poisson ?', 'URL']
    
    try:
        # Vérification si le fichier existe et s'il se termine par un saut de ligne
        file_needs_newline = False
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'rb') as f:
                f.seek(-1, os.SEEK_END)
                last_char = f.read(1)
                # Vérifie si le dernier caractère n'est PAS un saut de ligne
                if last_char not in (b'\n', b'\r'):
                    file_needs_newline = True

        # Ouverture en mode ajout ('a')
        with open(filepath, mode='a', encoding='utf-8', newline='') as csvfile:
            
            if file_needs_newline:
                csvfile.write('\n')

            # Utilisation de DictWriter
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            # Écriture de la nouvelle ligne
            writer.writerow(recipe_data)

        print(f"\n✅ Succès : La recette '{recipe_data['Titre']}' a été ajoutée manuellement à '{filepath}'.")
            
    except FileNotFoundError:
        print(f"Erreur: Le fichier cible '{filepath}' n'a pas été trouvé. Veuillez vérifier le chemin.")
    except Exception as e:
        print(f"Erreur lors de l'écriture du fichier CSV: {e}")


def main():
    """Fonction principale du script."""
    
    if not os.path.exists(RECIPE_FILE_PATH):
        print(f"Erreur: Le fichier des recettes '{RECIPE_FILE_PATH}' n'existe pas.")
        print("Veuillez vous assurer qu'il est bien présent avant d'exécuter le script.")
        sys.exit(1)

    # 1. Collecter les données de l'utilisateur
    new_recipe_details = collect_recipe_data()
    
    if new_recipe_details:
        # 2. Ajouter la nouvelle ligne au fichier CSV
        append_to_csv(new_recipe_details, RECIPE_FILE_PATH)


if __name__ == "__main__":
    main()