import os
from flask import Flask, render_template, request

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'turnstool-dev-key')

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/join', methods=['POST'])
def join():
    email = request.form.get('email')
    # TODO: Connect database to persist emails
    print(f"New waitlist sign-up: {email}")
    return render_template('index.html', joined=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
