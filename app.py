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
            expires_at TIMESTAMP,
            status TEXT DEFAULT 'active', -- 'active', 'expired', 'queued'
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

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT max_active_slots FROM categories WHERE id = ?', (category_id,))
    cat_row = cursor.fetchone()
    max_slots = cat_row['max_active_slots'] if cat_row else 10

    cursor.execute('SELECT COUNT(*) FROM queue_entries WHERE category_id = ? AND status = "active"', (category_id,))
    active_count = cursor.fetchone()[0]

    now = datetime.utcnow()

    if active_count < max_slots:
        status = 'active'
        expires_at = now + timedelta(minutes=60)
    else:
        status = 'queued'
        expires_at = None

    cursor.execute('''
        INSERT INTO queue_entries (category_id, title, author_name, content, created_at, expires_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (category_id, title, author_name, content, now, expires_at, status))
    
    entry_id = cursor.lastrowid
    conn.commit()

    cursor.execute('SELECT * FROM categories ORDER BY name ASC')
    categories = cursor.fetchall()
    conn.close()
    
    submitted_entry = {
        'id': entry_id,
        'title': title,
        'status': status
    }

    return render_template('submit.html', categories=categories, submitted_entry=submitted_entry)

@app.route('/feed', methods=['GET'])
def view_feed():
    category_filter = request.args.get('category', 'all')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.utcnow()
    
    # 1. Expire entries past their 60-minute window
    cursor.execute('''
        UPDATE queue_entries 
        SET status = 'expired' 
        WHERE status = 'active' AND expires_at <= ?
    ''', (now,))
    conn.commit()

    # 2. Check each category for open slots and promote queued items
    cursor.execute('SELECT id, max_active_slots FROM categories')
    all_categories = cursor.fetchall()
    
    for cat in all_categories:
        cat_id = cat['id']
        max_slots = cat['max_active_slots']
        
        cursor.execute('SELECT COUNT(*) FROM queue_entries WHERE category_id = ? AND status = "active"', (cat_id,))
        active_count = cursor.fetchone()[0]
        
        slots_needed = max_slots - active_count
        if slots_needed > 0:
            cursor.execute('''
                SELECT id FROM queue_entries 
                WHERE category_id = ? AND status = 'queued' 
                ORDER BY created_at ASC 
                LIMIT ?
            ''', (cat_id, slots_needed))
            queued_items = cursor.fetchall()
            
            for item in queued_items:
                new_expires = now + timedelta(minutes=60)
                cursor.execute('''
                    UPDATE queue_entries 
                    SET status = 'active', expires_at = ? 
                    WHERE id = ?
                ''', (new_expires, item['id']))
    
    conn.commit()
    
    # 3. Fetch active entries (Filtered or All)
    if category_filter != 'all':
        cursor.execute('''
            SELECT q.id, q.title, q.author_name, q.content, q.expires_at, c.name as category_name
            FROM queue_entries q
            JOIN categories c ON q.category_id = c.id
            WHERE q.status = 'active' AND q.category_id = ?
            ORDER BY q.created_at ASC
        ''', (category_filter,))
    else:
        cursor.execute('''
            SELECT q.id, q.title, q.author_name, q.content, q.expires_at, c.name as category_name
            FROM queue_entries q
            JOIN categories c ON q.category_id = c.id
            WHERE q.status = 'active'
            ORDER BY q.created_at ASC
        ''')
        
    raw_entries = cursor.fetchall()
    
    # Fetch all categories for the navigation header
    cursor.execute('SELECT * FROM categories ORDER BY name ASC')
    categories = cursor.fetchall()
    
    conn.close()
    
    entries = []
    for row in raw_entries:
        entry = dict(row)
        if isinstance(entry['expires_at'], str):
            entry['expires_iso'] = entry['expires_at'].replace(' ', 'T') + 'Z'
        else:
            entry['expires_iso'] = entry['expires_at'].isoformat() + 'Z'
        entries.append(entry)
    
    return render_template('feed.html', entries=entries, categories=categories, selected_category=category_filter)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
