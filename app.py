from __future__ import annotations

import os
import random
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "golf_charity.db"
UPLOAD_DIR = BASE_DIR / "uploads"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

MONTHLY_PLAN_PRICE = 49
YEARLY_PLAN_PRICE = 499
MIN_CHARITY_PERCENT = 10
PRIZE_POOL_PERCENT = 40
DEFAULT_DONATION_PERCENT = 15
DRAW_MATCHES = (5, 4, 3)
DRAW_SHARE_BY_MATCH = {5: 0.40, 4: 0.35, 3: 0.25}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


def using_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def _normalize_query(query: str) -> str:
    if using_postgres():
        return query.replace("?", "%s")
    return query


def _dict_rows(rows: list) -> list[dict]:
    return [dict(row) for row in rows]


def get_db():
    if "db" not in g:
        if using_postgres():
            if psycopg is None:
                raise RuntimeError("psycopg is required when DATABASE_URL points to PostgreSQL.")
            conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
            conn.autocommit = False
        else:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_: object | None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query_one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    row = get_db().execute(_normalize_query(query), params).fetchone()
    if row is None:
        return None
    return dict(row) if using_postgres() else row


def query_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    rows = get_db().execute(_normalize_query(query), params).fetchall()
    return _dict_rows(rows) if using_postgres() else rows


def execute(query: str, params: tuple = ()) -> int:
    conn = get_db()
    normalized = _normalize_query(query)
    if using_postgres() and query.lstrip().upper().startswith("INSERT INTO"):
        normalized = f"{normalized} RETURNING id"
        cur = conn.execute(normalized, params)
        inserted_id = cur.fetchone()["id"]
        conn.commit()
        return inserted_id
    cur = conn.execute(normalized, params)
    conn.commit()
    return getattr(cur, "lastrowid", 0)


def init_db() -> None:
    if using_postgres():
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL points to PostgreSQL.")
        db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        schema_path = BASE_DIR / "schema_postgres.sql"
    else:
        db = sqlite3.connect(DATABASE_PATH)
        schema_path = BASE_DIR / "schema.sql"
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

    schema = schema_path.read_text(encoding="utf-8")
    if using_postgres():
        with db.cursor() as cur:
            cur.execute(schema)
    else:
        db.executescript(schema)

    existing_admin = db.execute(_normalize_query("SELECT id FROM users WHERE email = ?"), ("admin@golfcharity.local",)).fetchone()
    if not existing_admin:
        admin_insert = _normalize_query(
            """
            INSERT INTO users (
                full_name, email, password_hash, role, selected_charity_id, charity_percentage, country_code
            ) VALUES (?, ?, ?, 'admin', NULL, ?, ?)
            """
        )
        db.execute(
            admin_insert,
            ("Platform Admin", "admin@golfcharity.local", generate_password_hash("admin12345"), MIN_CHARITY_PERCENT, "IN"),
        )

    charity_count_row = db.execute("SELECT COUNT(*) AS count FROM charities").fetchone()
    charities_count = charity_count_row["count"] if using_postgres() else charity_count_row[0]
    if charities_count == 0:
        charities = [
            (
                "Birdies For Better Futures",
                "Youth access to sport and education in underserved communities.",
                "children,sport,education",
                "India",
                "True",
                "https://images.unsplash.com/photo-1517486808906-6ca8b3f04846?auto=format&fit=crop&w=1200&q=80",
                "Charity golf day in Jaipur - April 18",
            ),
            (
                "Fairway Food Relief",
                "Monthly food-security drives sponsored through every active subscription.",
                "hunger,community,relief",
                "United Kingdom",
                "False",
                "https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?auto=format&fit=crop&w=1200&q=80",
                "Manchester fundraising scramble - May 03",
            ),
            (
                "Green Mile Health Fund",
                "Community health camps and rehabilitation support through golf-led giving.",
                "health,rehab,community",
                "United States",
                "False",
                "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?auto=format&fit=crop&w=1200&q=80",
                "Austin charity invitational - June 11",
            ),
        ]
        charity_insert = _normalize_query(
            """
            INSERT INTO charities (name, description, tags, country, is_featured, image_url, upcoming_event)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
        )
        db.executemany(charity_insert, charities)

    db.commit()
    db.close()


init_db()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            flash("Administrator access is required for that page.", "danger")
            return redirect(url_for("dashboard"))
        return view(**kwargs)

    return wrapped_view


def current_user() -> sqlite3.Row | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def active_subscription(user_id: int) -> sqlite3.Row | None:
    today = date.today().isoformat()
    return query_one(
        """
        SELECT * FROM subscriptions
        WHERE user_id = ? AND status = 'active' AND start_date <= ? AND end_date >= ?
        ORDER BY end_date DESC LIMIT 1
        """,
        (user_id, today, today),
    )


def ensure_subscription_status(user_id: int) -> None:
    execute(
        "UPDATE subscriptions SET status = 'lapsed' WHERE user_id = ? AND status = 'active' AND end_date < ?",
        (user_id, date.today().isoformat()),
    )


def create_subscription(user_id: int, plan: str, charity_percent: int) -> None:
    today = date.today()
    if plan == "yearly":
        price = YEARLY_PLAN_PRICE
        end_date = today + timedelta(days=365)
    else:
        plan = "monthly"
        price = MONTHLY_PLAN_PRICE
        end_date = today + timedelta(days=30)

    execute("UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ? AND status = 'active'", (user_id,))
    execute(
        """
        INSERT INTO subscriptions (user_id, plan, price, charity_percent, status, start_date, end_date)
        VALUES (?, ?, ?, ?, 'active', ?, ?)
        """,
        (user_id, plan, price, charity_percent, today.isoformat(), end_date.isoformat()),
    )
    queue_notification(user_id, "subscription", f"Your {plan} subscription is active until {end_date.isoformat()}.")


def queue_notification(user_id: int, kind: str, subject: str) -> None:
    execute(
        "INSERT INTO notifications (user_id, kind, subject, sent_at) VALUES (?, ?, ?, ?)",
        (user_id, kind, subject, datetime.utcnow().isoformat(timespec="seconds")),
    )


def latest_scores(user_id: int) -> list[sqlite3.Row]:
    return query_all(
        "SELECT * FROM scores WHERE user_id = ? ORDER BY played_at DESC, id DESC LIMIT 5",
        (user_id,),
    )


def enforce_five_score_limit(user_id: int) -> None:
    scores = query_all("SELECT id FROM scores WHERE user_id = ? ORDER BY played_at DESC, id DESC", (user_id,))
    for row in scores[5:]:
        execute("DELETE FROM scores WHERE id = ?", (row["id"],))


def get_user_ticket(user_id: int) -> list[int]:
    return [row["score"] for row in reversed(latest_scores(user_id))]


def weighted_draw_numbers() -> list[int]:
    all_scores = query_all(
        """
        SELECT s.score
        FROM scores s
        JOIN users u ON u.id = s.user_id
        JOIN subscriptions sub ON sub.user_id = u.id
        WHERE u.role = 'subscriber' AND sub.status = 'active'
        """
    )
    frequency = Counter(row["score"] for row in all_scores)
    pool = []
    for score in range(1, 46):
        pool.extend([score] * frequency.get(score, 1))
    numbers: list[int] = []
    while len(numbers) < 5:
        pick = random.choice(pool)
        if pick not in numbers:
            numbers.append(pick)
    return sorted(numbers)


def random_draw_numbers() -> list[int]:
    return sorted(random.sample(range(1, 46), 5))


def current_month_label() -> str:
    return date.today().strftime("%B %Y")


def current_draw() -> sqlite3.Row | None:
    return query_one("SELECT * FROM draws WHERE draw_month = ? ORDER BY id DESC LIMIT 1", (current_month_label(),))


def compute_prize_pool() -> dict[int, float]:
    active_subs = query_all("SELECT price FROM subscriptions WHERE status = 'active'")
    total_prize_pool = sum(row["price"] for row in active_subs) * (PRIZE_POOL_PERCENT / 100)
    return {match_count: round(total_prize_pool * share, 2) for match_count, share in DRAW_SHARE_BY_MATCH.items()}


def evaluate_draw(numbers: list[int], publish: bool, mode: str) -> dict:
    active_users = []
    for user in query_all("SELECT * FROM users WHERE role = 'subscriber'"):
        if active_subscription(user["id"]):
            active_users.append(user)
    prize_pool = compute_prize_pool()
    winners_by_match: dict[int, list[dict]] = {5: [], 4: [], 3: []}

    for user in active_users:
        ticket = get_user_ticket(user["id"])
        if len(ticket) < 5:
            continue
        match_count = len(set(ticket) & set(numbers))
        if match_count in winners_by_match:
            winners_by_match[match_count].append({"user_id": user["id"], "full_name": user["full_name"], "ticket": ticket})

    payout_by_match: dict[int, float] = {}
    rollover = 0.0
    for match_count in DRAW_MATCHES:
        winners = winners_by_match[match_count]
        if winners:
            payout_by_match[match_count] = round(prize_pool[match_count] / len(winners), 2)
        else:
            payout_by_match[match_count] = 0.0
            if match_count == 5:
                previous_rollover = query_one("SELECT rollover_amount FROM draws WHERE status = 'published' ORDER BY id DESC LIMIT 1")
                rollover = round(prize_pool[5] + (previous_rollover["rollover_amount"] if previous_rollover else 0), 2)

    draw_id = None
    if publish:
        draw_id = execute(
            """
            INSERT INTO draws (draw_month, mode, numbers, status, rollover_amount, simulated_at, published_at)
            VALUES (?, ?, ?, 'published', ?, ?, ?)
            """,
            (
                current_month_label(),
                mode,
                ",".join(str(num) for num in numbers),
                rollover,
                datetime.utcnow().isoformat(timespec="seconds"),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        for match_count, winners in winners_by_match.items():
            for winner in winners:
                execute(
                    """
                    INSERT INTO winners (draw_id, user_id, match_count, amount, payment_status, verification_status)
                    VALUES (?, ?, ?, ?, 'pending', 'awaiting-upload')
                    """,
                    (draw_id, winner["user_id"], match_count, payout_by_match[match_count]),
                )
                queue_notification(winner["user_id"], "winner", f"You matched {match_count} numbers in the {current_month_label()} draw.")
        for user in active_users:
            queue_notification(user["id"], "draw-result", f"{current_month_label()} draw results are now live.")

    return {
        "draw_id": draw_id,
        "numbers": numbers,
        "mode": mode,
        "winners_by_match": winners_by_match,
        "payout_by_match": payout_by_match,
        "prize_pool": prize_pool,
        "rollover": rollover,
    }


def reports_snapshot() -> dict:
    total_users = query_one("SELECT COUNT(*) AS count FROM users WHERE role = 'subscriber'")["count"]
    active_subs = query_all("SELECT price, charity_percent FROM subscriptions WHERE status = 'active'")
    total_prize_pool = round(sum(row["price"] for row in active_subs) * (PRIZE_POOL_PERCENT / 100), 2)
    charity_total = round(sum(row["price"] * (row["charity_percent"] / 100) for row in active_subs), 2)
    total_draws = query_one("SELECT COUNT(*) AS count FROM draws WHERE status = 'published'")["count"]
    pending_payouts = query_one("SELECT COUNT(*) AS count FROM winners WHERE payment_status = 'pending'")["count"]
    return {
        "total_users": total_users,
        "total_prize_pool": total_prize_pool,
        "charity_total": charity_total,
        "total_draws": total_draws,
        "pending_payouts": pending_payouts,
    }


@app.context_processor
def inject_globals() -> dict:
    return {"current_user": current_user(), "today": date.today(), "active_subscription": active_subscription, "current_year": date.today().year}


@app.route("/health")
def health():
    return {"status": "ok", "database": "postgres" if using_postgres() else "sqlite"}


@app.route("/")
def home():
    featured_charity = query_one("SELECT * FROM charities WHERE is_featured = 'True' ORDER BY id DESC LIMIT 1")
    charities = query_all("SELECT * FROM charities ORDER BY name ASC LIMIT 3")
    published_draw = query_one("SELECT * FROM draws WHERE status = 'published' ORDER BY id DESC LIMIT 1")
    return render_template("index.html", featured_charity=featured_charity, charities=charities, published_draw=published_draw, reports=reports_snapshot())


@app.route("/charities")
def charities():
    search = request.args.get("search", "").strip()
    country = request.args.get("country", "").strip()
    query = "SELECT * FROM charities WHERE 1=1"
    params: list[str] = []
    if search:
        query += " AND (name LIKE ? OR description LIKE ? OR tags LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if country:
        query += " AND country = ?"
        params.append(country)
    query += " ORDER BY is_featured DESC, name ASC"
    return render_template(
        "charities.html",
        charities=query_all(query, tuple(params)),
        countries=query_all("SELECT DISTINCT country FROM charities ORDER BY country ASC"),
        search=search,
        country=country,
    )


@app.route("/charities/<int:charity_id>")
def charity_detail(charity_id: int):
    charity = query_one("SELECT * FROM charities WHERE id = ?", (charity_id,))
    if not charity:
        flash("Charity not found.", "danger")
        return redirect(url_for("charities"))
    return render_template("charity_detail.html", charity=charity)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    charities_list = query_all("SELECT * FROM charities ORDER BY name ASC")
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        charity_id = int(request.form["charity_id"])
        charity_percentage = max(int(request.form["charity_percentage"]), MIN_CHARITY_PERCENT)
        plan = request.form["plan"]
        if query_one("SELECT id FROM users WHERE email = ?", (email,)):
            flash("That email is already registered.", "danger")
            return render_template("signup.html", charities=charities_list)
        user_id = execute(
            """
            INSERT INTO users (full_name, email, password_hash, role, selected_charity_id, charity_percentage, country_code)
            VALUES (?, ?, ?, 'subscriber', ?, ?, ?)
            """,
            (full_name, email, generate_password_hash(password), charity_id, charity_percentage, request.form.get("country_code", "IN").upper()),
        )
        create_subscription(user_id, plan, charity_percentage)
        session["user_id"] = user_id
        flash("Welcome aboard. Your subscription is active.", "success")
        return redirect(url_for("dashboard"))
    return render_template("signup.html", charities=charities_list)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = query_one("SELECT * FROM users WHERE email = ?", (email,))
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")
        session["user_id"] = user["id"]
        ensure_subscription_status(user["id"])
        flash(f"Welcome back, {user['full_name'].split()[0]}.", "success")
        return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    ensure_subscription_status(user["id"])
    selected_charity = query_one("SELECT * FROM charities WHERE id = ?", (user["selected_charity_id"],)) if user["selected_charity_id"] else None
    wins = query_all(
        """
        SELECT w.*, d.draw_month
        FROM winners w
        JOIN draws d ON d.id = w.draw_id
        WHERE w.user_id = ?
        ORDER BY w.id DESC
        """,
        (user["id"],),
    )
    return render_template(
        "dashboard.html",
        scores=latest_scores(user["id"]),
        subscription=active_subscription(user["id"]),
        selected_charity=selected_charity,
        wins=wins,
        notifications=query_all("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user["id"],)),
        current_draw_info=current_draw(),
        charities=query_all("SELECT * FROM charities ORDER BY name ASC"),
    )


@app.route("/subscription", methods=["POST"])
@login_required
def update_subscription():
    user = current_user()
    plan = request.form["plan"]
    charity_percentage = max(int(request.form["charity_percentage"]), MIN_CHARITY_PERCENT)
    execute("UPDATE users SET charity_percentage = ?, selected_charity_id = ? WHERE id = ?", (charity_percentage, int(request.form["charity_id"]), user["id"]))
    create_subscription(user["id"], plan, charity_percentage)
    flash("Subscription details updated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/subscription/cancel", methods=["POST"])
@login_required
def cancel_subscription():
    user = current_user()
    execute("UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ? AND status = 'active'", (user["id"],))
    queue_notification(user["id"], "subscription", "Your subscription has been cancelled.")
    flash("Your subscription has been cancelled.", "warning")
    return redirect(url_for("dashboard"))


@app.route("/scores/add", methods=["POST"])
@login_required
def add_score():
    user = current_user()
    if not active_subscription(user["id"]):
        flash("An active subscription is required to submit scores.", "danger")
        return redirect(url_for("dashboard"))
    score = int(request.form["score"])
    if not 1 <= score <= 45:
        flash("Scores must be between 1 and 45.", "danger")
        return redirect(url_for("dashboard"))
    execute("INSERT INTO scores (user_id, score, played_at) VALUES (?, ?, ?)", (user["id"], score, request.form["played_at"]))
    enforce_five_score_limit(user["id"])
    flash("Score added successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/scores/<int:score_id>/edit", methods=["POST"])
@login_required
def edit_score(score_id: int):
    user = current_user()
    score_row = query_one("SELECT * FROM scores WHERE id = ? AND user_id = ?", (score_id, user["id"]))
    if not score_row:
        flash("Score entry not found.", "danger")
        return redirect(url_for("dashboard"))
    score = int(request.form["score"])
    if not 1 <= score <= 45:
        flash("Scores must be between 1 and 45.", "danger")
        return redirect(url_for("dashboard"))
    execute("UPDATE scores SET score = ?, played_at = ? WHERE id = ?", (score, request.form["played_at"], score_id))
    flash("Score updated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/donate", methods=["POST"])
@login_required
def donate():
    user = current_user()
    charity_id = int(request.form["charity_id"])
    execute(
        "INSERT INTO donations (user_id, charity_id, amount, donated_at) VALUES (?, ?, ?, ?)",
        (user["id"], charity_id, float(request.form["amount"]), datetime.utcnow().isoformat(timespec="seconds")),
    )
    charity = query_one("SELECT * FROM charities WHERE id = ?", (charity_id,))
    queue_notification(user["id"], "donation", f"Independent donation recorded for {charity['name']}.")
    flash("Donation recorded successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/winner-proof/<int:winner_id>", methods=["POST"])
@login_required
def upload_winner_proof(winner_id: int):
    user = current_user()
    winner = query_one("SELECT * FROM winners WHERE id = ? AND user_id = ?", (winner_id, user["id"]))
    if not winner:
        flash("Winner record not found.", "danger")
        return redirect(url_for("dashboard"))
    file = request.files.get("proof")
    if not file or not file.filename:
        flash("Please upload a screenshot for verification.", "danger")
        return redirect(url_for("dashboard"))
    UPLOAD_DIR.mkdir(exist_ok=True)
    filename = secure_filename(f"{uuid4().hex}{Path(file.filename).suffix.lower()}")
    file.save(UPLOAD_DIR / filename)
    execute("UPDATE winners SET proof_path = ?, verification_status = 'under-review' WHERE id = ?", (filename, winner_id))
    flash("Proof uploaded. An admin will review it shortly.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    users = query_all(
        """
        SELECT u.*, c.name AS charity_name
        FROM users u
        LEFT JOIN charities c ON c.id = u.selected_charity_id
        ORDER BY u.id DESC
        """
    )
    scores = query_all(
        """
        SELECT s.*, u.full_name
        FROM scores s
        JOIN users u ON u.id = s.user_id
        ORDER BY s.played_at DESC, s.id DESC
        """
    )
    winners = query_all(
        """
        SELECT w.*, u.full_name, d.draw_month
        FROM winners w
        JOIN users u ON u.id = w.user_id
        JOIN draws d ON d.id = w.draw_id
        ORDER BY w.id DESC
        """
    )
    return render_template(
        "admin.html",
        users=users,
        scores=scores,
        subscriptions=query_all("SELECT s.*, u.full_name FROM subscriptions s JOIN users u ON u.id = s.user_id ORDER BY s.id DESC"),
        charities=query_all("SELECT * FROM charities ORDER BY is_featured DESC, name ASC"),
        winners=winners,
        draws=query_all("SELECT * FROM draws ORDER BY id DESC"),
        reports=reports_snapshot(),
        simulation=session.pop("draw_simulation", None),
    )


@app.route("/admin/users/<int:user_id>/subscription", methods=["POST"])
@login_required
@admin_required
def admin_update_user_subscription(user_id: int):
    execute(
        "UPDATE subscriptions SET status = ? WHERE id = (SELECT id FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1)",
        (request.form["status"], user_id),
    )
    flash("Subscription status updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<int:user_id>/charity", methods=["POST"])
@login_required
@admin_required
def admin_update_user_charity(user_id: int):
    execute(
        "UPDATE users SET selected_charity_id = ?, charity_percentage = ? WHERE id = ?",
        (int(request.form["charity_id"]), max(int(request.form["charity_percentage"]), MIN_CHARITY_PERCENT), user_id),
    )
    flash("User charity settings updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/scores/<int:score_id>", methods=["POST"])
@login_required
@admin_required
def admin_edit_score(score_id: int):
    execute("UPDATE scores SET score = ?, played_at = ? WHERE id = ?", (int(request.form["score"]), request.form["played_at"], score_id))
    owner = query_one("SELECT user_id FROM scores WHERE id = ?", (score_id,))
    if owner:
        enforce_five_score_limit(owner["user_id"])
    flash("Score updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/charities", methods=["POST"])
@login_required
@admin_required
def admin_create_charity():
    execute(
        """
        INSERT INTO charities (name, description, tags, country, is_featured, image_url, upcoming_event)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.form["name"],
            request.form["description"],
            request.form["tags"],
            request.form["country"],
            request.form.get("is_featured", "False"),
            request.form["image_url"],
            request.form["upcoming_event"],
        ),
    )
    flash("Charity added.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/charities/<int:charity_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_charity(charity_id: int):
    execute("DELETE FROM charities WHERE id = ?", (charity_id,))
    flash("Charity removed.", "warning")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/draw/simulate", methods=["POST"])
@login_required
@admin_required
def simulate_draw():
    mode = request.form["mode"]
    result = evaluate_draw(weighted_draw_numbers() if mode == "algorithmic" else random_draw_numbers(), publish=False, mode=mode)
    session["draw_simulation"] = {
        "mode": result["mode"],
        "numbers": result["numbers"],
        "payout_by_match": result["payout_by_match"],
        "winner_counts": {str(match): len(result["winners_by_match"][match]) for match in DRAW_MATCHES},
        "prize_pool": result["prize_pool"],
        "rollover": result["rollover"],
    }
    flash("Simulation completed. Review the forecast before publishing.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/draw/publish", methods=["POST"])
@login_required
@admin_required
def publish_draw():
    mode = request.form["mode"]
    if current_draw():
        flash("This month already has a recorded draw.", "danger")
        return redirect(url_for("admin_dashboard"))
    evaluate_draw(weighted_draw_numbers() if mode == "algorithmic" else random_draw_numbers(), publish=True, mode=mode)
    flash("Draw published successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/winners/<int:winner_id>/verify", methods=["POST"])
@login_required
@admin_required
def verify_winner(winner_id: int):
    verification_status = request.form["verification_status"]
    payment_status = request.form["payment_status"]
    execute("UPDATE winners SET verification_status = ?, payment_status = ? WHERE id = ?", (verification_status, payment_status, winner_id))
    winner = query_one("SELECT * FROM winners WHERE id = ?", (winner_id,))
    if winner:
        queue_notification(winner["user_id"], "winner-review", f"Your winner verification is now {verification_status}.")
    flash("Winner record updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reports")
@login_required
@admin_required
def reports():
    donations = query_all(
        """
        SELECT d.amount, d.donated_at, c.name AS charity_name, u.full_name
        FROM donations d
        JOIN charities c ON c.id = d.charity_id
        JOIN users u ON u.id = d.user_id
        ORDER BY d.id DESC
        """
    )
    return render_template("reports.html", reports=reports_snapshot(), donations=donations)


@app.route("/seed-demo")
def seed_demo():
    if query_one("SELECT COUNT(*) AS count FROM users WHERE role = 'subscriber'")["count"] > 0:
        flash("Demo data already exists.", "warning")
        return redirect(url_for("home"))
    charity_id = query_one("SELECT id FROM charities ORDER BY id LIMIT 1")["id"]
    demo_users = [("Aarav Mehta", "aarav@example.com"), ("Emily Carter", "emily@example.com"), ("Rohan Kapoor", "rohan@example.com")]
    for index, (full_name, email) in enumerate(demo_users, start=1):
        user_id = execute(
            """
            INSERT INTO users (full_name, email, password_hash, role, selected_charity_id, charity_percentage, country_code)
            VALUES (?, ?, ?, 'subscriber', ?, ?, ?)
            """,
            (full_name, email, generate_password_hash("password123"), charity_id, DEFAULT_DONATION_PERCENT + index, "IN"),
        )
        create_subscription(user_id, "monthly" if index != 2 else "yearly", DEFAULT_DONATION_PERCENT + index)
        for offset in range(5):
            execute("INSERT INTO scores (user_id, score, played_at) VALUES (?, ?, ?)", (user_id, random.randint(18, 42), (date.today() - timedelta(days=offset * 7 + index)).isoformat()))
        enforce_five_score_limit(user_id)
    flash("Demo accounts and sample scores have been created.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    init_db()
    app.run(debug=True)
