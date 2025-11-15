import streamlit as st
import pandas as pd
import json
import os
import re
import time
import requests
from collections import defaultdict
from typing import List, Dict, Any
from dotenv import load_dotenv
import datetime
from fpdf import FPDF
import urllib.parse


# Charger les variables d'environnement depuis le fichier .env
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Configuration et Chemins de Fichiers ---
RECIPE_CSV_PATH = "files/recipes.csv"
INGREDIENT_CACHE_PATH = "files/all_categorized_ingredients_cache.json"
AVAILABLE_JSON_PATH = "files/categorized_available_ingredients.json"
AVAILABLE_CSV_PATH = "files/available_ingredients.csv"
MEAL_PLAN_PATH = "files/weekly_meal_plan.md"
GROCERY_LIST_PATH = "files/weekly_shopping_list.md"
URL_RECIPE_FILE_PATH = "files/URL_recipes.csv"
FILES_DIR = "files"
GROCERY_LIST_PATH_TXT = "files/weekly_shopping_list.txt"

# Ensure the 'files' directory exists
os.makedirs(FILES_DIR, exist_ok=True)

# --- Gemini API Setup ---
# Key is read from environment variable GEMINI_API_KEY
API_KEY = GOOGLE_API_KEY
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={API_KEY}"
MODEL = "gemini-2.5-flash-preview-09-2025"
MAX_RETRIES = 5

def api_call(payload: Dict[str, Any], system_prompt: str, response_schema: Dict[str, Any]) -> str | None:
    """Handles the API call with structured output and exponential backoff."""
    if not API_KEY:
        st.error("GEMINI_API_KEY environment variable is not set. Please set it to use AI features.")
        return None

    full_payload = {
        "contents": payload['contents'],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                f"{API_URL}",
                headers={'Content-Type': 'application/json'},
                data=json.dumps(full_payload),
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            # Handle potential empty text response
            if result.get('candidates') and result['candidates'][0]['content']['parts'][0].get('text'):
                return result['candidates'][0]['content']['parts'][0]['text']
            else:
                st.error("API returned no text content or an unexpected structure.")
                return None

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt
                print(f"API request failed (Attempt {attempt+1}/{MAX_RETRIES}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                st.error(f"Failed to get AI response after {MAX_RETRIES} attempts. Error: {e}")
                return None
        except Exception as e:
            st.error(f"Error processing AI response: {e}")
            return None
    return None

# --- Data Loading and Initialization ---

@st.cache_data
def load_recipe_data() -> pd.DataFrame:
    """Loads the master recipe CSV into a DataFrame."""
    try:
        # Load, ensuring correct columns exist
        df = pd.read_csv(RECIPE_CSV_PATH)
        required_cols = ['Titre', 'Ingrédients Clés', 'Préparation (min)', 'Cuisson (min)', 'Contient viande/poisson ?', 'URL']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ''
        return df[required_cols]
    except FileNotFoundError:
        st.error(f"Erreur: Le fichier de recettes `{RECIPE_CSV_PATH}` est introuvable. Veuillez le créer.")
        return pd.DataFrame(columns=required_cols)
    except Exception as e:
        st.error(f"Erreur lors du chargement du fichier CSV: {e}")
        return pd.DataFrame(columns=required_cols)

# --- Inventory Tab Functions (Gemini Categorization) ---

def clean_ingredient_list(df: pd.DataFrame) -> List[str]:
    """Extracts, cleans, and deduplicates all ingredients."""
    if 'Ingrédients Clés' not in df.columns: return []
    all_ingredients = set()
    for item in df['Ingrédients Clés'].dropna():
        # Split by comma and clean whitespace
        ingredients = [re.sub(r'\s+', ' ', ing.strip()) for ing in item.split(',')]
        for ing in ingredients:
            if ing:
                all_ingredients.add(ing)
    return sorted(list(all_ingredients))

def get_categorized_ingredients(ingredients: List[str]) -> Dict[str, List[str]]:
    """Uses Gemini to categorize the list of ingredients, with caching."""
    # 1. Check cache
    if os.path.exists(INGREDIENT_CACHE_PATH):
        try:
            with open(INGREDIENT_CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            st.warning("Cache d'ingrédients corrompu. Re-génération via AI.")

    if not API_KEY:
        return {"Tous les Ingrédients": ingredients} # Fallback

    # 2. Define AI task and schema
    system_prompt = (
        "You are an expert culinary assistant. Your task is to categorize a list of raw ingredients "
        "into logical groups. Return the output as a single JSON object conforming to the provided schema. "
        "The category names should be in French, and every ingredient provided in the input must be present in exactly one category in the output."
    )
    user_query = f"Categorize the following ingredients: {', '.join(ingredients)}"
    response_schema = {
        "type": "OBJECT", "description": "A mapping of ingredient categories to a list of ingredients.",
        "properties": {"Catégories": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "category_name": {"type": "STRING", "description": "The name of the category (e.g., 'Légumes')."},
            "ingredients": {"type": "ARRAY", "items": {"type": "STRING"}}
        }, "required": ["category_name", "ingredients"]}}}
    }
    payload = {"contents": [{"parts": [{"text": user_query}]}]}

    # 3. Call API
    with st.spinner("Première exécution : l'IA classe vos ingrédients..."):
        json_text = api_call(payload, system_prompt, response_schema)

    if json_text:
        try:
            parsed_json = json.loads(json_text)
            categorized_dict = {}
            for item in parsed_json.get('Catégories', []):
                categorized_dict[item['category_name']] = item['ingredients']
            
            # 4. Save cache
            with open(INGREDIENT_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(categorized_dict, f, ensure_ascii=False, indent=2)
            return categorized_dict
        except Exception as e:
            st.error(f"Erreur de décodage JSON de l'IA: {e}")
            return {"Tous les Ingrédients": ingredients}
    
    return {"Tous les Ingrédients": ingredients} # Final Fallback

def save_available_ingredients(categorized_inventory: Dict[str, List[str]], flat_inventory: List[str]):
    """Saves the user's selected inventory to both JSON and CSV files."""
    with open(AVAILABLE_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(categorized_inventory, f, ensure_ascii=False, indent=2)

    df_csv = pd.DataFrame(flat_inventory, columns=['Ingrédient'])
    df_csv.to_csv(AVAILABLE_CSV_PATH, index=False, header=True, encoding='utf-8')
    st.success(f"Inventaire enregistré ! Fichiers mis à jour dans `{FILES_DIR}/`.")

# --- Recipe Management Tab Functions ---

def append_recipe_to_csv(new_recipe: Dict[str, str]):
    """Appends a new recipe to the master CSV file."""
    try:
        df_new_row = pd.DataFrame([new_recipe])
        df_recipes = load_recipe_data()
        
        # Concatenate and save
        df_updated = pd.concat([df_recipes, df_new_row], ignore_index=True)
        df_updated.to_csv(RECIPE_CSV_PATH, index=False, encoding='utf-8')
        
        st.cache_data.clear() # Clear Streamlit cache to force reload
        st.success(f"Recette '{new_recipe['Titre']}' ajoutée avec succès à la base de données.")
    except Exception as e:
        st.error(f"Erreur lors de l'ajout au CSV : {e}")

def add_recipe_from_url_ai(url: str):
    """Uses Gemini to scrape recipe data from a URL and append it."""
    st.info("Requête AI en cours pour extraire les données de la recette...")
    
    system_prompt = (
        "You are an expert web scraper for culinary data. Extract the required fields from the provided recipe URL. "
        "The output MUST be a JSON object conforming exactly to the schema. "
        "Ensure 'Préparation (min)' and 'Cuisson (min)' are integers representing minutes. "
        "'Contient viande/poisson ?' MUST be either 'Oui' or 'Non' in French."
        "The 'Ingrédients Clés' should be a comma-separated list of the main, most generic ingredients."
    )
    user_query = f"Extract recipe data from this URL: {url}"

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "Titre": {"type": "STRING"},
            "Ingrédients Clés": {"type": "STRING", "description": "Comma-separated list of key ingredients."},
            "Préparation (min)": {"type": "NUMBER"},
            "Cuisson (min)": {"type": "NUMBER"},
            "Contient viande/poisson ?": {"type": "STRING", "enum": ["Oui", "Non"]},
            "URL": {"type": "STRING"}
        },
        "required": ["Titre", "Ingrédients Clés", "Préparation (min)", "Cuisson (min)", "Contient viande/poisson ?", "URL"]
    }

    payload = {"contents": [{"parts": [{"text": user_query}]}]}
    
    with st.spinner("Extraction des données via Gemini..."):
        json_text = api_call(payload, system_prompt, response_schema)

    if json_text:
        try:
            new_recipe = json.loads(json_text)
            new_recipe['URL'] = url # Ensure the URL is correctly saved
            
            # Type correction for numeric fields (AI might return float)
            new_recipe['Préparation (min)'] = int(new_recipe.get('Préparation (min)', 0))
            new_recipe['Cuisson (min)'] = int(new_recipe.get('Cuisson (min)', 0))

            append_recipe_to_csv(new_recipe)
            st.rerun() # Refresh to show new count
        except Exception as e:
            st.error(f"Erreur de traitement de la réponse AI pour l'extraction : {e}")

# --- Planner Tab Function (Gemini Meal Planning) ---

def create_pdf_bytes_shopping_list(data):
    """
    Crée un document PDF à partir du dictionnaire de la liste de courses
    et retourne le contenu du fichier en mémoire (bytes).
    
    Utilise la police 'Arial' et remplace le caractère de puce Unicode '•' par '*' 
    pour éviter les erreurs d'encodage.
    """
    
    # 1. Initialisation du PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.add_page()
    
    # Définition de la police de base à 'Arial' pour le support des accents simples
    BASE_FONT = 'Arial'
    
    # 2. Titre
    pdf.set_font(BASE_FONT, style='B', size=18)
    # L'encodage 'latin-1' aide souvent FPDF avec les accents français
    pdf.cell(0, 10, 'Liste de Courses', 0, 1, 'C') 
    
    # 3. Date
    pdf.set_font(BASE_FONT, style='', size=10)
    pdf.cell(0, 5, f"Date de génération : {datetime.date.today().strftime('%d/%m/%Y')}", 0, 1, 'C')
    pdf.ln(5)

    # 4. Itération sur les catégories et les articles
    for category_key, items in data.items():
        # Utilisation de .title() pour formater les catégories
        formatted_category = category_key.replace("_", " ").title().replace(" ", " / ")
        
        # En-tête de catégorie
        pdf.set_font(BASE_FONT, style='B', size=14)
        pdf.set_fill_color(230, 240, 255) # Couleur de fond légère
        pdf.cell(0, 8, formatted_category, 0, 1, 'L', 1) 
        
        # Articles
        pdf.set_font(BASE_FONT, style='', size=12)
        if items:
            for item in items:
                # Ajout de l'article avec une puce simple ('*') au lieu de l'Unicode ('•')
                pdf.write(6, '* ')
                pdf.write(6, item)
                pdf.ln(6) # Retour à la ligne pour l'article suivant
        else:
            pdf.cell(0, 6, '(Aucun article)', 0, 1, 'L')
        
        pdf.ln(4)

    # Retourne le contenu du PDF en bytes
    return pdf.output() 


def generate_meal_plan_ai(df_recipes: pd.DataFrame, num_days: int):
    """
    Calculates feasibility (missing ingredients score) and calls Gemini to generate the final meal plan.
    This logic strictly follows the 'menu_generator' format.
    """
    st.info(f"Préparation des données pour le Planificateur AI pour {num_days} jours...")

    # 1. Load available ingredients
    if not os.path.exists(AVAILABLE_CSV_PATH):
        st.error("Inventaire non trouvé. Veuillez d'abord compléter l'onglet 'Mon Inventaire' et cliquer sur 'Enregistrer l'Inventaire'.")
        return

    df_available = pd.read_csv(AVAILABLE_CSV_PATH)
    # Use set comprehension for quick lookup, ensuring consistent cleaning (strip/lowercase)
    available_ingredients = {ing.strip().lower() for ing in df_available['Ingrédient'].dropna()}
    
    if not available_ingredients:
        st.error("Aucun ingrédient n'est disponible. Veuillez sélectionner votre inventaire.")
        return
        
    st.write(f"Inventaire chargé ({len(available_ingredients)} ingrédients uniques).")


   
    # Format data for the AI prompt
    # Select only the relevant columns the AI needs to plan (Titre, Ingrédients Clés, etc., plus the Score)
    recipes_for_ai = df_recipes
    
    # Convert to JSON string
    recipes_json = recipes_for_ai.to_json(orient='records', indent=2, force_ascii=False)
    
    # Format available ingredients for context
    available_str = ', '.join(sorted([ing.title() for ing in available_ingredients])) # Title case for better readability in prompt
    
    # 3. Construct the Gemini Prompt (updated for Lunch and Dinner)
    system_prompt = (
            "Tu es un assistant expert en planification de repas. "
            f"Tu crées un plan de repas pour {num_days} jours (midi et soir) et une liste de courses. "
            "Tu te bases sur une liste de recettes fournie en JSON et des contraintes spécifiques. "
            "Tu réponds TOUJOURS au format JSON en respectant le schéma demandé."
        )

    user_prompt = f"""
        Voici la liste complète des recettes disponibles au format JSON :
        {recipes_json}

        Veuillez maintenant générer un plan de repas en respectant IMPÉRATIVEMENT les contraintes suivantes :
        1.  **Ingrédients disponibles :** J'ai déjà {available_str}. Vous devez prioriser les recettes qui utilisent ces ingrédients.
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

 #       response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=60)

            



        # 5. Call API
    with st.spinner(f"L'IA est en train d'établir votre menu pour {num_days} jours (Déjeuner et Dîner)..."):
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=60)
        response_data = response.json()
        # Extraire le texte JSON de la réponse de l'API
        json_text = response_data['candidates'][0]['content']['parts'][0]['text']
        print(json_text)

    if json_text:
        try:
            plan_data = json.loads(json_text)
            
            # Convert JSON plan to a Markdown table for display
            plan_markdown = "## Plan de Repas Généré par Gemini Cuisinier\n\n"
            
            # Display Remarks first
            plan_markdown += f"### Remarques de l'IA\n{plan_data.get('Remarques', 'Aucune remarque fournie.')}\n\n---\n"
            
            # Display the table
            plan_markdown += "| Jour | Déjeuner | Dîner |\n"
            plan_markdown += "| :--- | :--- | :--- |\n"
            
            # Check if Plan de Repas is a list and contains items
            if 'plan_repas' in plan_data and isinstance(plan_data['plan_repas'], list):
                for item in plan_data['plan_repas']:
                    
                    dejeuner = item.get('midi', {})
                    print(dejeuner)
                    diner = item.get('soir', {})
                    
                    #dejeuner_str = f"**{dejeuner.get('titre', 'N/A')}** ({dejeuner.get('url', 'N/A')})"
                    dejeuner_str = f"[{dejeuner.get('titre', 'N/A')}]({dejeuner.get('url', 'N/A')})"
                    diner_str = f"[{diner.get('titre', 'N/A')}]({diner.get('url', 'N/A')})"
                    
                    plan_markdown += f"| {item.get('jour', '')} | {dejeuner_str} | {diner_str} |\n"
            else:
                plan_markdown += "| N/A | Le plan de repas n'a pas été généré correctement. | | |\n"

            # Save the plan
            with open(MEAL_PLAN_PATH, 'w', encoding='utf-8') as f:
                f.write(plan_markdown)
                
            st.success("Plan de repas généré avec succès !")
            st.markdown(plan_markdown)
            
            #st.info("Note : Pour voir les ingrédients clés de chaque plat, reportez-vous à la base de données de recettes.")
            
        except Exception as e:
            st.error(f"Erreur lors du traitement du plan de repas AI : {e}. Contenu brut : {json_text}")
    else:
        st.error("Échec de la génération du plan de repas. Veuillez vérifier la configuration de l'API.")

    # Titre de l'application
    GROCERY_LIST = plan_data['liste_courses']
    st.title("🛒 Votre Liste de Courses")
    st.info("Voici les ingrédients classés par catégorie pour vos achats.")
    
    # 1. Générer les bytes du PDF
    #pdf_bytes = create_pdf_bytes_shopping_list(GROCERY_LIST)

    # 2. Afficher le bouton de téléchargement
   # col1, col2 = st.columns([1, 4])
    #with col1:
    #    st.download_button(
    #        label="📄 Télécharger en PDF",
    #        data=pdf_bytes,
    #        file_name=f"Liste_Courses_{datetime.date.today().strftime('%Y-%m-%d')}.pdf",
    #        mime="application/pdf",
    #        help="Cliquez pour obtenir une version imprimable de votre liste."
    #   )

    
    # Définition des titres et icônes pour chaque catégorie
    category_titles = {
        "viande_poisson": "🥩 Viande & Poisson",
        "laitiers_frais": "🧀 Produits Laitiers & Frais",
        "legumes_feculents": "🥦 Légumes & Féculents",
        "epicerie": "🥫 Épicerie Sèche"
    }

    # Utiliser des colonnes Streamlit pour afficher les catégories côte à côte
    cols = st.columns(len(GROCERY_LIST))

    # Itérer sur les catégories et leurs articles
    record ='SHOPPING LIST'+ "\n" 
    for i, (category_key, items) in enumerate(GROCERY_LIST.items()):
        # Récupérer le titre formaté
        title = category_titles.get(category_key, category_key.replace("_", " ").title())
        
        with cols[i]:
            # Afficher le titre de la catégorie
            st.markdown(f"#### {title}")
            
            # Utiliser st.markdown avec des puces (tirets) pour une liste simple
            if items:
                # Créer une chaîne Markdown pour la liste non ordonnée
                list_markdown = "\n".join([f"- {item}" for item in items])
                record = record + "\n" + "\n" + f'{title}' + "\n" + f'{list_markdown}'
                st.markdown(list_markdown)
            else:
                st.markdown("_(Aucun article)_")

    # Save the list
    with open(GROCERY_LIST_PATH, 'w', encoding='utf-8') as f:
        f.write(record)

    with open(GROCERY_LIST_PATH_TXT, 'w', encoding='utf-8') as f:
        f.write(record)
       
    st.success("Liste de courses générée avec succès !")

    # Bouton de téléchargement
   # st.download_button(
    #    label="💾 Télécharger la liste de course",
    #    data=record,
    #    file_name="shopping_list.txt",
   ##     mime="text/plain",
   #     help="Cliquez pour télécharger le fichier"
   # )


    # 1. Préparer le nom du fichier
    file_name = "weekly_shopping_list.txt"

    # 2. Encoder le contenu pour qu'il soit sûr d'être placé dans une URL (Data URI)
    # La Data URI est de la forme: data:[<MIME-type>][;charset=<encoding>][;base64],<data>
    # Nous utilisons 'text/plain;charset=utf-8'
    encoded_content = urllib.parse.quote(record)
    data_uri = f"data:text/plain;charset=utf-8,{encoded_content}"

    # 3. Créer le lien HTML
    html_download_link = f"""
    <a href="{data_uri}" download="{file_name}" target="_blank" 
    style="display: inline-flex; align-items: center; justify-content: center; 
            background-color: #4CAF50; color: white; padding: 10px 24px; 
            text-align: center; text-decoration: none; border-radius: 8px; 
            font-weight: bold; border: none; cursor: pointer;">
        💾 Télécharger la Liste de Courses
    </a>
    """

    # 4. Afficher le lien HTML dans Streamlit
    st.markdown(html_download_link, unsafe_allow_html=True)




# --- Streamlit Application Layout ---

def app_main():
    """Main function to run the Streamlit application."""
    st.set_page_config(
        page_title="Planificateur de Menus Gemini",
        layout="wide",
        initial_sidebar_state="auto"
    )

    st.title("🍽️ Planificateur de Menus Hebdomadaire (AI-Powered)")
    st.subheader("Optimisez vos recettes et votre inventaire grâce à Mimil the meal planner.")

    # Load master data once
    df_recipes = load_recipe_data()
    st.sidebar.info(f"Recettes en Base de Données : {len(df_recipes)}")

    tab1, tab2, tab3 = st.tabs(["1. Gestion des Recettes", "2. Mon Inventaire", "3. Planificateur IA"])

    # ====================================================================
    # TAB 1: Recipe Management
    # ====================================================================
    with tab1:
        st.header("Gestion et Expansion de la Base de Recettes")

        mode = st.radio("Comment voulez-vous ajouter une recette ?", 
                        ("Ajout par URL (AI)", "Ajout Manuel"), horizontal=True)

        if mode == "Ajout Manuel":
            st.subheader("➕ Ajout Manuel d'une Nouvelle Recette")
            with st.form("manual_recipe_form"):
                title = st.text_input("Titre de la Recette")
                key_ingredients = st.text_area("Ingrédients Clés (séparés par des virgules)")
                prep_time = st.number_input("Temps de Préparation (min)", min_value=1, value=10)
                cook_time = st.number_input("Temps de Cuisson (min)", min_value=1, value=15)
                is_meat = st.selectbox("Contient viande/poisson ?", ["Non", "Oui"])
                url_field = st.text_input("URL Source (optionnel)")
                
                submitted = st.form_submit_button("Enregistrer la Recette Manuellement")

                if submitted:
                    if not title or not key_ingredients:
                        st.error("Le Titre et les Ingrédients Clés sont obligatoires.")
                    else:
                        new_recipe = {
                            'Titre': title,
                            'Ingrédients Clés': key_ingredients,
                            'Préparation (min)': prep_time,
                            'Cuisson (min)': cook_time,
                            'Contient viande/poisson ?': is_meat,
                            'URL': url_field
                        }
                        append_recipe_to_csv(new_recipe)
                        st.experimental_rerun() # Refresh to show new count

        elif mode == "Ajout par URL (AI)":
            st.subheader("🌐 Ajout de Recette par URL (Assisté par IA)")
            url_input = st.text_input("Entrez l'URL de la Recette", key="url_input")
            if st.button("Extraire et Ajouter la Recette via AI"):
                if url_input:
                    add_recipe_from_url_ai(url_input)
                else:
                    st.warning("Veuillez entrer une URL valide.")

        st.markdown("---")
        st.subheader("Base de Données Actuelle")
        st.dataframe(df_recipes, height=300)

    # ====================================================================
    # TAB 2: Inventory Selection
    # ====================================================================
    with tab2:
        st.header("🛒 Mon Inventaire d'Ingrédients")
        st.markdown("Sélectionnez les ingrédients que vous avez actuellement à disposition. L'AI les utilisera comme contrainte principale.")

        all_unique_ingredients = clean_ingredient_list(df_recipes)
        if not all_unique_ingredients:
            st.warning("Aucun ingrédient n'a pu être extrait. Vérifiez votre fichier CSV de recettes.")
            # Do not stop, just show the message

        # Get categorized list (uses cache or API call)
        categorized_ingredients = get_categorized_ingredients(all_unique_ingredients)

        if 'inventory' not in st.session_state:
            # Try to load existing available ingredients on first load
            if os.path.exists(AVAILABLE_CSV_PATH):
                try:
                    df_initial = pd.read_csv(AVAILABLE_CSV_PATH)
                    st.session_state.inventory = list(df_initial['Ingrédient'].dropna().unique())
                except:
                    st.session_state.inventory = []
            else:
                 st.session_state.inventory = []
        
        available_ingredients_list = []
        
        st.subheader("Catégories d'Ingrédients")
        
        col_count = 3
        
        for category, ingredients in categorized_ingredients.items():
            st.markdown(f"### {category}")
            ingredients.sort()

            cols = st.columns(col_count)
            
            for i, ing in enumerate(ingredients):
                col = cols[i % col_count]
                
                # Checkbox state is determined by session_state on first run
                is_checked = col.checkbox(
                    ing, 
                    value=(ing in st.session_state.inventory), # Use inventory state for initial value
                    key=f"check_{ing}"
                )
                if is_checked:
                    available_ingredients_list.append(ing)

        # Update session state with the current selection
        st.session_state.inventory = available_ingredients_list

        st.markdown("---")
        st.metric(label="Ingrédients Sélectionnés", value=len(st.session_state.inventory))
        
        if st.button("✅ Enregistrer l'Inventaire", key="save_inventory_btn"):
            if not st.session_state.inventory:
                st.warning("Veuillez sélectionner au moins un ingrédient avant d'enregistrer.")
            else:
                final_categorized_inventory = defaultdict(list)
                selected_set = set(st.session_state.inventory)
                
                # Re-categorize the selected items for the JSON output
                for category, ingredients in categorized_ingredients.items():
                    for ing in ingredients:
                        if ing in selected_set:
                            final_categorized_inventory[category].append(ing)
                            
                save_available_ingredients(dict(final_categorized_inventory), st.session_state.inventory)
                st.balloons()
                
    # ====================================================================
    # TAB 3: AI Meal Planner
    # ====================================================================
    with tab3:
        st.header("🤖 Planification Automatisée des Repas")
        st.markdown("L'IA utilise votre inventaire enregistré pour générer un plan de repas qui maximise l'utilisation des ingrédients disponibles.")

        num_days = st.slider("Nombre de jours à planifier", min_value=1, max_value=7, value=5)

        if os.path.exists(AVAILABLE_CSV_PATH):
            df_inventory = pd.read_csv(AVAILABLE_CSV_PATH)
            st.success(f"Inventaire trouvé : **{len(df_inventory)} ingrédients** disponibles.")
        else:
            st.warning("Inventaire non trouvé. Veuillez enregistrer vos ingrédients dans l'onglet 'Mon Inventaire'.")
            
        st.markdown("---")

        if st.button(f"✨ Générer le Menu pour {num_days} Jours (Déjeuner & Dîner via Gemini)"):
            if os.path.exists(AVAILABLE_CSV_PATH) and len(df_recipes) > 0:
                generate_meal_plan_ai(df_recipes, num_days)
            else:
                st.error("Impossible de générer : Assurez-vous d'avoir enregistré votre inventaire et d'avoir des recettes dans la base de données.")


if __name__ == "__main__":
    app_main()