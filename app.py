from flask import Flask, jsonify, render_template, request, redirect, session, flash, url_for
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
from werkzeug.utils import secure_filename
app = Flask(__name__)

# Secret key for session
app.secret_key = "hajhfsdllajfkds"

# Folder to save uploaded images
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Configuration
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "recipe"

SPOONACULAR_API_KEY="bec2204f34be4336845b7e8635ebe4a4"
# Function to Connect to Database
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if conn.is_connected():
            return conn
    except Error as e:
        print(f"❌ Error Connecting to Database: {e}")
        return None

# Home Page
@app.route('/')
def home():
    return render_template('home.html')

# Registration Page (GET & POST)
@app.route('/registration', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if passwords match
        if password != confirm_password:
            return '''<script>alert("Passwords do not match!"); window.location.href="/registration";</script>'''

        # Hash the password
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
            existing_user = cursor.fetchone()

            if existing_user:
                return '''<script>alert("Username or Email already exists!"); window.location.href="/registration";</script>'''

            # Insert new user
            cursor.execute("INSERT INTO users (full_name, email, username, password_hash) VALUES (%s, %s, %s, %s)",
                           (full_name, email, username, hashed_password))
            conn.commit()
            cursor.close()
            conn.close()

            # Show success alert and redirect to login
            return '''<script>alert("Registration successful! Please log in."); window.location.href="/login";</script>'''

    return render_template('registration.html')

# Login Page (GET & POST)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user and check_password_hash(user['password_hash'], password):  
                session['user_id'] = user['user_id']
                session['username'] = user['username']

                return '''<script>alert("Login successful! Redirecting to dashboard..."); window.location.href="/dashboard";</script>'''

            else:
             
                return '''<script>alert("Invalid username or password!"); window.location.href="/login";</script>'''

    return render_template('login.html')


# Dashboard Route (After Successful Login)  
@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        return render_template('dashboard.html', username=session['username'])  # Pass username to template
    else:
        return redirect('/login') 
    
@app.route('/profile')    
def profile():
    if 'user_id' not in session:
        flash("Please log in first!", "danger")
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT full_name, email, username, created_at FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    
    cursor.close()
    conn.close()

    if not user:
        flash("User not found!", "danger")
        return redirect('/login')

    return render_template('profile.html', user=user)


@app.route('/get_user_profile')
def get_user_profile():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT full_name, email, username, created_at FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            return user

    return {}


# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect('/login')

@app.route('/process_ingredients', methods=['POST'])
def process_ingredients():
    text_ingredients = request.form.get('ingredients')
    image_file = request.files.get('image')
    ingredients_list = []

    # Add text ingredients
    if text_ingredients:
        ingredients_list.extend([ing.strip() for ing in text_ingredients.split(',')])

    # Process image input
    if image_file:
        files = {'file': (image_file.filename, image_file.stream, image_file.mimetype)}
        headers = {"x-api-key": SPOONACULAR_API_KEY}
        response = requests.post("https://api.spoonacular.com/food/images/analyze", files=files, headers=headers)


        if response.status_code == 200:
            data = response.json()
            extracted_ingredients = [item['name'] for item in data.get('ingredients', [])]
            ingredients_list.extend(extracted_ingredients)
        else:
            flash("⚠️ Could not analyze image. Please try again.", "warning")
            return redirect(url_for('dashboard'))

    if not ingredients_list:
        flash("⚠️ No ingredients found! Try entering them manually.", "warning")
        return redirect(url_for('dashboard'))

    final_ingredients = ",".join(set(ingredients_list))    
    api_url = f"https://api.spoonacular.com/recipes/findByIngredients?ingredients={final_ingredients}&number=5&apiKey={SPOONACULAR_API_KEY}"
    response = requests.get(api_url)

    if response.status_code == 200 and response.json():
        recipes = response.json()

        # Fetch calories for each recipe
        for recipe in recipes:
            recipe_id = recipe["id"]
            nutrition_url = f"https://api.spoonacular.com/recipes/{recipe_id}/nutritionWidget.json?apiKey={SPOONACULAR_API_KEY}"
            nutrition_response = requests.get(nutrition_url)

            if nutrition_response.status_code == 200:
                nutrition_data = nutrition_response.json()
                recipe["calories"] = nutrition_data.get("calories", "N/A")
            else:
                recipe["calories"] = "N/A"

        return render_template('generated_recipe.html', recipes=recipes)
    else:
        flash("⚠️ No recipes found for the given ingredients.", "warning")
        return redirect(url_for('dashboard'))

@app.route('/full_recipe/<int:recipe_id>')
def full_recipe(recipe_id):
    api_url = f"https://api.spoonacular.com/recipes/{recipe_id}/information?includeNutrition=true&apiKey={SPOONACULAR_API_KEY}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()

        # Extract nutritional information
        nutrition = data.get('nutrition', {})
        calories = None
        if 'nutrients' in nutrition:
            for nutrient in nutrition['nutrients']:
                if nutrient['name'] == 'Calories':
                    calories = nutrient['amount']
                    break

        # Extract dietary preferences
        dietary_preferences = []
        if data.get('vegetarian'):
            dietary_preferences.append('Vegetarian')
        if data.get('vegan'):
            dietary_preferences.append('Vegan')
        if data.get('glutenFree'):
            dietary_preferences.append('Gluten-Free')
        if data.get('dairyFree'):
            dietary_preferences.append('Dairy-Free')
        # Add more preferences as needed

        # Handle missing ingredients safely
        ingredients = []
        if "extendedIngredients" in data:
            ingredients = [
                {"name": ing.get("name", "Unknown"), "amount": ing.get("amount", ""), "unit": ing.get("unit", "")}
                for ing in data["extendedIngredients"]
            ]

        # Handle missing instructions safely
        instructions = []
        if "analyzedInstructions" in data and data["analyzedInstructions"]:
            instructions = [step["step"] for step in data["analyzedInstructions"][0].get("steps", [])]

        recipe = {
            "id": recipe_id,
            "title": data.get("title", "No Title"),
            "image": data.get("image", ""),
            "ingredients": ingredients,
            "instructions": instructions if instructions else ["No instructions available."],
            "calories": calories,
            "dietary_preferences": dietary_preferences,
            "precautions": "Ensure all ingredients are fresh and properly cooked to avoid foodborne illness."
        }
        return render_template('full_recipe.html', recipe=recipe)
    else:
        flash("Error fetching full recipe details.", "danger")
        return redirect(url_for('dashboard'))



# Contact Us Page (GET & POST)
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        subject = request.form['subject']
        message = request.form['message']

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                sql = "INSERT INTO contact_messages (full_name, email, subject, message) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (full_name, email, subject, message))
                conn.commit()
                cursor.close()
                conn.close()
                
                # Return success response after insertion
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        else:
            return jsonify({"success": False, "error": "Database connection failed"})

    return render_template('contact.html')

# Route to render the All Recipes Page
@app.route('/all_recipes')
def all_recipes():
    number_of_recipes = 100  # Fetch 18 recipes at once
    api_url = f"https://api.spoonacular.com/recipes/random?number={number_of_recipes}&apiKey={SPOONACULAR_API_KEY}"
    
    response = requests.get(api_url)
    if response.status_code == 200:
        data = response.json()
        recipes = data.get("recipes", [])
        return render_template('all_recipes.html', recipes=recipes)
    else:
        return "Failed to fetch recipes. Please try again later."


@app.route("/about")
def about():
    return render_template("about.html")

@app.route('/add_favorite', methods=['POST'])
def add_favorite():
    if 'user_id' not in session:
        flash("Please log in to save recipes!", "danger")
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    recipe_id = request.form['recipe_id']
    title = request.form['title']
    image = request.form['image']

    # Check if recipe already exists in favorites
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM saved_recipes WHERE user_id=%s AND recipe_id=%s", (user_id, recipe_id))
        existing = cursor.fetchone()

        if existing:
            flash("This recipe is already in your favorites!", "warning")
        else:
            cursor.execute("INSERT INTO saved_recipes (user_id, recipe_id, title, image_url) VALUES (%s, %s, %s, %s)",
                       (user_id, recipe_id, title, image))
        conn.commit()
        flash("Recipe added to favorites!", "success")

    return redirect(request.referrer)

@app.route('/saved_recipes')
def saved_recipes():
    if 'user_id' not in session:
        return "Please log in first!", 403  # Restrict access if not logged in

    user_id = session['user_id']  # Get the logged-in user's ID

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch only the saved recipes for the logged-in user
    cursor.execute("SELECT recipe_id, title, image_url FROM saved_recipes WHERE user_id = %s", (user_id,))
    saved_recipes = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('saved_recipes.html', saved_recipes=saved_recipes)

@app.route('/remove_saved_recipe', methods=['POST'])
def remove_saved_recipe():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "User not logged in"}), 403

    data = request.get_json()
    recipe_id = data.get("recipe_id")
    user_id = session["user_id"]

    if not recipe_id:
        return jsonify({"success": False, "error": "Recipe ID missing"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Remove the saved recipe from the database
    cursor.execute("DELETE FROM saved_recipes WHERE user_id = %s AND recipe_id = %s", (user_id, recipe_id))
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"success": True})
if __name__ == '__main__':
    app.run(debug=True)
