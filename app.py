from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3, uuid, json
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.jinja_env.filters['loads'] = json.loads
app.secret_key = 'your_secret_key'
DB_NAME = 'membership.db'

# -------------------- 資料庫初始化 -------------------- #
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 訂單
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            table_number TEXT,
            customer_name TEXT,
            items TEXT,
            total INTEGER,
            status TEXT DEFAULT '尚未接單',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 意見
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 會員
    c.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            table_number TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------- 共用函式 -------------------- #
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_NAME)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login_user', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

# -------------------- 模擬菜單 -------------------- #
menu_items = [
    {"id": 1, "name": "牛肉麵", "price": 120, "image": "beef_noodle.jpg"},
    {"id": 2, "name": "滷肉飯", "price": 60, "image": "pork_rice.jpg"},
    {"id": 3, "name": "雞排便當", "price": 90, "image": "chicken_bento.jpg"}
]

# -------------------- 前台路由 -------------------- #
@app.route('/')
def home():
    return redirect(url_for('login_user'))

@app.route('/menu')
@login_required
def menu():
    return render_template('index.html', menu=menu_items)

@app.route('/cart')
@login_required
def cart():
    return render_template('cart.html', menu=menu_items)


@app.route('/submit_order', methods=['POST'])
@login_required
def submit_order():
    order_data = request.form

    table_number = session.get('table_number', '未指定')
    customer_name = session.get('user_name', '訪客')
    order_id = str(uuid.uuid4())[:8]

    order_items = []
    total = 0
    for item in menu_items:
        qty = int(order_data.get(str(item['id']), 0))
        if qty > 0:
            order_items.append({
                'name': item['name'],
                'quantity': qty,
                'price': item['price']
            })
            total += item['price'] * qty

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (id, customer_name, table_number, items, total)
        VALUES (?, ?, ?, ?, ?)
    ''', (order_id, customer_name, table_number, json.dumps(order_items), total))
    conn.commit()

    return render_template('order_result.html',
                           order_id=order_id,
                           table_number=table_number,
                           order_items=order_items,
                           total=total)

@app.route('/history')
@login_required
def order_history():
    table_number = session.get('table_number')
    conn = get_db()
    cursor = conn.cursor()
    cutoff = datetime.now() - timedelta(days=30)
    cursor.execute("SELECT * FROM orders WHERE table_number = ? AND created_at >= ?", (table_number, cutoff))
    orders = cursor.fetchall()
    return render_template("history.html", orders=orders, searched=True)

@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    submitted = False
    if request.method == 'POST':
        table_number = session.get('table_number')
        message = request.form['message']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO feedback (table_number, message) VALUES (?, ?)', (table_number, message))
        conn.commit()
        submitted = True
    return render_template('feedback.html', submitted=submitted)

# -------------------- 會員系統 -------------------- #

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO members (name, email, password) VALUES (?, ?, ?)', (name, email, hashed_pw))
            conn.commit()
            return redirect('/login_user')
        except sqlite3.IntegrityError:
            error = "此 Email 已註冊過"
    return render_template('register.html', error=error)




@app.route('/login_user', methods=['GET', 'POST'])
def login_user():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM members WHERE email = ?', (email,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect('/input_table')
        else:
            error = "帳號或密碼錯誤"
    return render_template('login_user.html', error=error)





@app.route('/logout_user')
def logout_user():
    session.clear()
    return redirect('/login_user')



# -------------------- 商家後台 -------------------- #
ADMIN_PASSWORD = 'admin123'


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session.clear()
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            error = "密碼錯誤"
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect('/login')



@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect('/login')
    selected_status = request.args.get("status")
    conn = get_db()
    cursor = conn.cursor()
    if selected_status:
        cursor.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", (selected_status,))
    else:
        cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    orders = cursor.fetchall()

    parsed_orders = []
    for order in orders:
        parsed_order = dict(order)
        try:
            parsed_order['items'] = json.loads(order['items']) if order['items'] else []
        except Exception as e:
            print(f"⚠️ 訂單 {order['id']} 的 items 解析失敗：{e}")
            parsed_order['items'] = [{"name": "錯誤資料", "quantity": "-", "price": "-"}]
        parsed_orders.append(parsed_order)

    return render_template("admin.html", orders=parsed_orders, selected_status=selected_status)



@app.route('/update_status', methods=['POST'])
def update_status():
    if not session.get('admin_logged_in'):
        return redirect('/login')
    order_id = request.form['order_id']
    new_status = request.form['new_status']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    return redirect('/admin')

if __name__ == '__main__':
    app.run(debug=True)


@app.route('/track')
@login_required
def track_order():
    order_id = request.args.get("order_id")
    order = None
    if order_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
    return render_template("track.html", order=order, searched=bool(order_id))



@app.route('/input_table', methods=['GET', 'POST'])
@login_required
def input_table():
    if request.method == 'POST':
        table_number = request.form['table_number']
        session['table_number'] = table_number
        return redirect('/menu')
    return render_template('input_table.html')
