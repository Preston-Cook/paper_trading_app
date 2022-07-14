import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Collect all holdings data
    user_id = session["user_id"]
    aggregate_data = db.execute("SELECT * FROM holdings WHERE user_id = ? AND shares != 0 ORDER BY shares DESC", user_id)

    # Initialize list
    stock_lst = []

    # Initialize Grand Total
    grand_total = 0

    # Loop Through Stocks
    for stock in aggregate_data:
        stock_dic = {}
        api_response = lookup(stock["symbol"])
        stock_dic["name"] = api_response["name"]
        stock_dic["symbol"] = api_response["symbol"]
        stock_dic["shares"] = stock["shares"]
        stock_dic["current_price"] = api_response["price"]
        stock_dic["holding_value"] = stock_dic["shares"] * stock_dic["current_price"]
        grand_total += stock_dic["holding_value"]
        stock_dic["holding_value"] = usd(stock_dic["holding_value"])
        stock_dic["current_price"] = usd(stock_dic["current_price"])
        stock_lst.append(stock_dic)

    # Retrieve cash balance
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = float(cash_db[0]["cash"])

    # Calculate Grand Total
    grand_total += cash

    # Render index.html
    return render_template("index.html", stock_lst=stock_lst, cash=usd(cash),grand_total=usd(grand_total))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # Render buy.html if GET request
    if request.method == "GET":
        return render_template("buy.html")

    # Retrieve form data
    symbol = request.form.get("symbol")
    shares = request.form.get("shares")

    # Input validation
    if not symbol:
        return apology("Enter a Symbol")
    elif not shares:
        return apology("Enter a Number of Shares")

    #Testing for positive numeric shares
    try:
        shares = int(shares)
        assert shares > 0
    except:
        return apology("Enter a Valid Number of Shares")

    # Ensure symbol is valid
    api_response = lookup(symbol)
    if not api_response:
        return apology("Enter a Valid Symbol")

    # Calculate Transaction Cost
    cost = api_response["price"] * shares

    # Retrieve current cash
    user_id = session["user_id"]
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = float(cash_db[0]["cash"])

    # Validate user's funds
    if cash < cost:
        return apology("Insufficient Funds")

    # Log transaction
    db.execute("INSERT INTO transactions(user_id, name, symbol, transaction_type, shares, price, time) VALUES(?, ?, ?, ?, ?, ?, ?)", user_id, api_response["name"], symbol, "PURCHASE", shares, api_response["price"], datetime.now())

    # Update cash
    new_cash = cash - cost
    db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

    # Update  holdings

    # Check if stock already in holdings
    holdings = db.execute("SELECT * FROM holdings WHERE symbol = ? AND user_id = ?", symbol, user_id)

    # Create new row if stock not in holdings
    if not holdings:
        db.execute("INSERT INTO holdings(user_id, name, symbol, shares) VALUES(?, ?, ?, ?)", user_id, api_response["name"], symbol, shares)
    else:
        # Update shares if found
        new_shares = int(holdings[0]["shares"]) + shares
        db.execute("UPDATE holdings SET shares = ? WHERE user_id = ? AND symbol = ?", new_shares, user_id, symbol)

    # Notify User of Success
    name = api_response["name"]
    flash(f"Successfully Purchased {shares} share(s) of {name} for {usd(cost)}!")

    # Redirect User to Index
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Retrieve user id from session
    user_id = session["user_id"]

    # Retrieve all transactions from user
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY time DESC", user_id)

    # Return history.html
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # Render quote.html if GET request
    if request.method == "GET":
        return render_template("quote.html")

    # Collect form data
    symbol = request.form.get("symbol").upper()

    # Receive and check API response
    api_response = lookup(symbol)
    if not api_response:
        return apology("Invalid Symbol")

    # Render quoted.html
    return render_template("quoted.html", stock_data=api_response)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Collect form data
    if request.method == "GET":
        return render_template("register.html")

    # Else for POST request
    username = request.form.get("username")
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")

    # Check for blank input
    if not username:
        return apology("Enter a Username")
    elif not password:
        return apology("Enter a Password")
    elif not confirmation:
        return apology("Enter a Confirmation")

    # Make sure confirmation matches password
    if password != confirmation:
        return apology("Passwords Do Not Match")

    # Check if username already exists
    username_exists = db.execute("SELECT username FROM users WHERE username = ?", username)
    if username_exists != []:
        return apology("Username Already Exists")

    # Hash Password
    hash = generate_password_hash(password)

    # Add user to Database
    db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username, hash)

    # Find new user's id
    user_id = db.execute("SELECT id FROM users WHERE username = ?", username)

    # Set session to user's id
    session["user_id"] = user_id[0]["id"]

    # Redirect user to index
    return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Retrieve Current User's ID
    user_id = session["user_id"]

    # Render sell.html if GET request
    if request.method == "GET":

        # Check for Owned Stocks
        stocks_owned = db.execute("SELECT symbol FROM holdings WHERE user_id = ? AND shares != 0 ORDER BY symbol", user_id)
        return render_template("sell.html", stocks_owned=stocks_owned)

    # Retrieve form data
    symbol = request.form.get("symbol")
    shares = request.form.get("shares")

    # Input validation
    if not symbol:
        return apology("Enter a Symbol")
    elif not shares:
        return apology("Enter a Number of Shares")

    #Testing for positive numeric shares
    try:
        shares = int(shares)
        assert shares > 0
    except:
        return apology("Enter a Valid Number of Shares")

    # Ensure symbol is valid
    api_response = lookup(symbol)
    if not api_response:
        return apology("Enter a Valid Symbol")

    # Calculate transaction gain on sale
    gain = api_response["price"] * shares

    # Retrieve current cash
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = float(cash_db[0]["cash"])

    # Validate user has enough shares
    current_shares_db = db.execute("SELECT * FROM holdings WHERE symbol = ? AND user_id = ?", symbol, user_id)
    current_shares = int(current_shares_db[0]["shares"])
    if current_shares < shares:
        return apology("You Do Not Have Enough Shares")

    # Log transaction
    db.execute("INSERT INTO transactions(user_id, name, symbol, transaction_type, shares, price, time) VALUES(?, ?, ?, ?, ?, ?, ?)", user_id, api_response["name"], symbol, "SALE", shares, api_response["price"], datetime.now())

    # Update Cash
    new_cash = cash + gain
    db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

    # Update Holdings
    new_shares = current_shares - shares
    db.execute("UPDATE holdings SET shares = ? WHERE user_id = ? AND symbol = ?", new_shares, user_id, symbol)

    # Notify User of Success
    name = api_response["name"]
    flash(f"Successfully Sold {shares} share(s) of {name} for {usd(gain)}!")

    # Redirect User to Index
    return redirect("/")