import os
import sqlite3
from flask import Flask, render_template, request

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'turnstool-dev-key')
DB_FILE = 'waitlist.db'

def init_db():
    """Creates the waitlist table if it doesn't already exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Initialize database table on app startup
init_db()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/join', methods=['POST'])
def join():
    email = request.form.get('email', '').strip()
    if email:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO waitlist (email) VALUES (?)', (email,))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            # Handles duplicate sign-ups gracefully
            pass
    return render_template('index.html', joined=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
