import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'turnstool-dev-key')
DB_FILE = 'waitlist.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Returns dict-like rows for easy JSON/template usage
    return conn

def init_db():
    """Initializes schema for waitlist, categories, and queue rotation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Waitlist Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. Categories Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            max_active_slots INTEGER DEFAULT 10
        )
    ''')
    
    # Seed initial categories if empty
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ('Fiction', 'fiction', 10),
            ('Non-Fiction', 'non-fiction', 10),
            ('Poetry', 'poetry', 10),
            ('Sci-Fi & Fantasy', 'sci-fi-fantasy', 10)
        ]
        cursor.executemany(
            'INSERT INTO categories (name, slug, max_active_slots) VALUES (?, ?, ?)', 
            default_categories
        )

    # 3. FIFO Queue Entries Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            author_name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'active', -- 'active', 'expired', 'queued'
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    conn.commit()
    conn.close()

# Initialize tables at boot
init_db()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/join', methods=['POST'])
def join():
    email = request.form.get('email', '').strip()
    if email:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO waitlist (email) VALUES (?)', (email,))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            pass  # Ignore duplicate emails
    return render_template('index.html', joined=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
