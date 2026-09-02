import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'turnstool-dev-key')
DB_FILE = 'waitlist.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            max_active_slots INTEGER DEFAULT 10
        )
    ''')
    
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            author_name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    conn.commit()
    conn.close()

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
            pass
    return render_template('index.html', joined=True)

@app.route('/submit', methods=['GET'])
def render_submit():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories ORDER BY name ASC')
    categories = cursor.fetchall()
    conn.close()
    return render_template('submit.html', categories=categories)

@app.route('/submit', methods=['POST'])
def submit_entry():
    category_id = request.form.get('category_id')
    title = request.form.get('title', '').strip()
    author_name = request.form.get('author_name', '').strip()
    content = request.form.get('content', '').strip()
    
    if not (category_id and title and author_name and content):
        return jsonify({'error': 'Missing required fields'}), 400

    expires_at = datetime.utcnow() + timedelta(minutes=60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO queue_entries (category_id, title, author_name, content, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (category_id, title, author_name, content, expires_at))
    conn.commit()
    conn.close()
    
    return redirect('/feed')

@app.route('/feed', methods=['GET'])
def view_feed():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.utcnow()
    cursor.execute('''
        UPDATE queue_entries 
        SET status = 'expired' 
        WHERE status = 'active' AND expires_at <= ?
    ''', (now,))
    conn.commit()
    
    cursor.execute('''
        SELECT q.id, q.title, q.author_name, q.content, q.expires_at, c.name as category_name
        FROM queue_entries q
        JOIN categories c ON q.category_id = c.id
        WHERE q.status = 'active'
        ORDER BY q.created_at ASC
        LIMIT 10
    ''')
    raw_entries = cursor.fetchall()
    conn.close()
    
    entries = []
    for row in raw_entries:
        entry = dict(row)
        if isinstance(entry['expires_at'], str):
            entry['expires_iso'] = entry['expires_at'].replace(' ', 'T') + 'Z'
        else:
            entry['expires_iso'] = entry['expires_at'].isoformat() + 'Z'
        entries.append(entry)
    
    return render_template('feed.html', entries=entries)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
