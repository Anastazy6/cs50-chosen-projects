import os

from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")






@app.route("/")
@app.route("/<alert>")
@login_required
def index(alert=""):
    """Show portfolio of stocks"""
    user_id = session['user_id']
    stonks = db.execute("SELECT symbol, company_name, shares FROM owned_stonks WHERE user_id = ? \
            ORDER BY symbol", user_id)

    user_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = float(user_cash[0]['cash'])
    total_stonks_value = 0

    # get the current price for each owned stock, total value of a company's stocks and total value of all owned stocks
    for stonk in stonks:

        # Update data
        current_stonk_data = lookup(stonk["symbol"])
        stonk['price'] = float(current_stonk_data['price'])
        stonk['total_price'] = round(int(stonk['shares']) * float(stonk['price']), 2)
        total_stonks_value += float(stonk['total_price'])

        # Format money data to USD format
        stonk['price'] = usd(stonk['price'])
        stonk['total_price'] = usd(stonk['total_price'])


    total_stonks_value = round(total_stonks_value, 2)
    cash = round(cash, 2)
    total_cash = cash + total_stonks_value

    return render_template("portfolio.html", alert=alert, stonks=stonks, cash=usd(cash), total_cash=usd(total_cash))



# Holds all users currently performing any buy/sell operation to prevent spamming (and giving them free credit)
users_submitting_forms = set()

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Store both the username (just in case #todelete) and the user's balace
        user_id = session['user_id']

        try:
            assert user_id not in users_submitting_forms
            users_submitting_forms.add(user_id)


            user_data = db.execute("SELECT username, cash FROM users where id = ?", user_id)
            username = user_data[0]["username"]
            cash = float(user_data[0]["cash"])

            # Get the API values, return apology if symbol is invalid
            symbol = request.form.get("symbol")
            api_values = lookup(symbol)
            # api_values format: {'name': '<company name>', 'price': <share price>, 'symbol': <The same symbol as above>}

            if api_values == None:
                return apology(f"Symbol {symbol} not found")

            # number of shares bought
            try:
                shares = int(request.form.get("shares"))
                if shares < 1:
                    return apology("LOL U CANOT BUY SO LITL")
            except TypeError:
                return apology("WTF U EV'N ENTERED")
            # price of one share
            share_price = float(api_values["price"])
            # company name that will be in the database for clarity
            company_name = api_values['name']

            print(api_values, shares)

            # Returns apology if the user cannot afford the purchase
            total_cost = shares * share_price
            if total_cost > cash:
                return apology("LOL U POOR")

            updated_cash = cash - total_cost

            operation = "BUY"
            transaction_time = datetime.now()
            transaction_time = transaction_time.strftime("%Y-%m-%d %H:%M:%S")

            owned_stonks = db.execute("SELECT shares FROM owned_stonks WHERE user_id = ? AND \
                    symbol = ?", user_id, symbol)

            if len(owned_stonks) == 0:
                db.execute("INSERT INTO owned_stonks (user_id, symbol, company_name, shares) VALUES \
                        (?, ?, ?, ?)", user_id, symbol, company_name, shares)
            else:
                owned_shares = int(owned_stonks[0]['shares'])
                total_shares = owned_shares + shares
                db.execute("UPDATE owned_stonks SET shares = ? WHERE user_id = ? AND \
                        symbol = ?", total_shares, user_id, symbol)

            db.execute("INSERT INTO history (user_id, symbol, company_name, shares, \
                    share_price, total_cost, operation, datetime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    user_id, symbol, company_name, shares, share_price, total_cost, operation, transaction_time)


            db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, user_id)


            return redirect("/")

        except AssertionError:
            alert = f"Buy button spam clicking detected! Buy operation successful,\
                    prevented giving the user additional stocks for free."

            print("A user was trying to spam \"buy\" button.")
            return redirect(url_for(".index", alert = alert))
    else:
        if session["user_id"] in users_submitting_forms:
            users_submitting_forms.remove(session["user_id"])
        return render_template("buy.html")





@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session['user_id']

    deals = db.execute("SELECT * FROM history WHERE user_id = ? ORDER BY datetime DESC", user_id)


    for deal in deals:
        deal['share_price'] = usd(deal['share_price'])
        deal['total_cost'] = usd(deal['total_cost'])



    return render_template("history.html", deals=deals)





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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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

    if request.method == "POST":

        symbol = request.form.get("symbol")
        api_values = lookup(symbol)

        if api_values == None:
            return apology(f"Symbol {symbol} not found")

        return render_template("quoted.html", company=api_values['name'], symbol=api_values['symbol'],
                usd_price=usd(api_values['price']))


    else:
        return render_template("quote.html")






@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    session.clear()

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password was succesfully confirmed
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("password and confirmation must be the same", 403)

        # Ensure that the submitted username is uniquie (i.e. it's not in the database yet)
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        if len(rows) != 0:
            return apology("username is already taken")

        else:
            username = request.form.get("username")
            hashish = generate_password_hash(request.form.get("password"))

            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hashish)

        user_id = db.execute("SELECT id FROM users WHERE username = ?", username)
        user_id = user_id[0]["id"]
        session["user_id"] = user_id


        alert = "Registration successful!"
        return redirect(url_for(".index", alert=alert))

    else:
        return render_template("register.html")







@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        user_id = session['user_id']
        try:
            assert user_id not in users_submitting_forms
            users_submitting_forms.add(user_id)



            stonk_to_sell_symbol = request.form.get("symbol")
            try:
                shares_to_sell = int(request.form.get("shares"))
                if shares_to_sell < 1:
                    return apology("LOL U DUMB U CANOT SEL SO FYOOW")
            except TypeError:
                return apology("WTF U EV'N ENTERED?")

            owned_shares = db.execute("SELECT shares FROM owned_stonks WHERE user_id = ? AND symbol = ?",
                    user_id, stonk_to_sell_symbol)

            # checks if the user has 1) ANY stocks of a given company; 2) at least as mamy stocks of that type as he/she wants to sell
            if len(owned_shares) == 0:
                return apology(f"U NO HAV {stonk_to_sell_symbol} STONKS")
            elif int(owned_shares[0]["shares"] < int(shares_to_sell)):
                return apology(f"U NO HAV DIS MANY {stonk_to_sell_symbol} STONKS")

            # the user wouldn't be able to buy stocks of a non-existent company so there's no need to check whether the symbol is valid
            updated_stonk_data = lookup(stonk_to_sell_symbol)

            share_price = round(float(updated_stonk_data["price"]), 2)
            total_cost = share_price * shares_to_sell
            company_name = updated_stonk_data['name']

            cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
            cash = round(float(cash[0]["cash"]), 2)
            new_cash = cash + total_cost
            new_owned_shares = owned_shares[0]["shares"] - shares_to_sell

            # Set the user's cash to the new value
            db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

            # Set the user's shares value to the new value. In case of selling out all stocks of a type,
            # remove the entry from the database. Protected from giving the user free cash in case of
            # the programmer fucking up his job.
            if new_owned_shares > 0:
                db.execute("UPDATE owned_stonks SET shares = ? WHERE symbol = ? AND \
                        user_id = ?", new_owned_shares, stonk_to_sell_symbol, user_id)
            elif new_owned_shares == 0:
                db.execute("DELETE FROM owned_stonks WHERE symbol = ? AND user_id = ?",
                stonk_to_sell_symbol, user_id)
            else:
                # No cash for free in case of a critical error
                db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, user_id)
                return apology("IF U SEE DIS NOW DE PROGRAMMER HAZ FUCKED UP")

            # Update history
            operation = "SELL"
            transaction_time = datetime.now()
            transaction_time = transaction_time.strftime("%Y-%m-%d %H:%M:%S")

            db.execute("INSERT INTO history (user_id, symbol, company_name, shares, \
                    share_price, total_cost, operation, datetime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    user_id, stonk_to_sell_symbol, company_name, shares_to_sell,
                    share_price, total_cost, operation, transaction_time)



            return redirect("/")

        except AssertionError:
            alert = f"Sell button spam clicking detected! Sell operation successful,\
                    prevented taking extra stocks from the user without paying for them."
            print("A user was trying to spam \"sell\" button.")
            return redirect(url_for(".index", alert=alert))
    else:
        if session["user_id"] in users_submitting_forms:
            users_submitting_forms.remove(session["user_id"])


        owned_stonks = db.execute("SELECT symbol FROM owned_stonks WHERE user_id = ?", session["user_id"])

        return render_template("sell.html", owned_stonks=owned_stonks)







@app.route("/manage_account")
@login_required
def manage_account():
    """Allows the user to manage their account (i.e. to change password, add/withdraw money or whatever)"""

    user_data = db.execute("SELECT username, cash FROM users WHERE id = ?", session['user_id'])
    username = user_data[0]["username"]
    cash = usd(round(float(user_data[0]["cash"]), 2))
    return render_template("manage_account.html", cash=cash, username=username)







@app.route("/update_cash", methods=["POST"])
@login_required
def update_cash():
    """Allows the user to add (well, "add") or withdraw (well, "withdraw") cash from the account"""

    user_id = session['user_id']
    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = float(cash[0]["cash"])

    dollars = int(request.form.get("dollars")) * 100
    cents = int(request.form.get("cents"))
    cash_modification = round((dollars + cents) / 100, 2)

    try:
        action = request.form.get("action")
        assert action in ["add", "withdraw"]
    except AssertionError:
        return apology("IF U SEE DIS NOW DE PROGRAMMER HAZ FUCKED UP")

    transaction_time = datetime.now()
    transaction_time = transaction_time.strftime("%Y-%m-%d %H:%M:%S")

    if action == "add":

        operation = "SEND CASH"
        new_cash = cash + cash_modification

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

        db.execute("INSERT INTO history (user_id, symbol, company_name, shares, share_price, total_cost, \
                operation, datetime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", user_id, "SYSTEM", "System operation",
                0, 0, cash_modification, operation, transaction_time)
        alert = "Money added successfully!"

    else:

        new_cash = cash - cash_modification
        operation = "WITHDRAW CASH"

        if new_cash < 0:
            return apology("LOL U POOR")

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

        db.execute("INSERT INTO history (user_id, symbol, company_name, shares, share_price, total_cost, \
        operation, datetime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", user_id, "SYSTEM", "System operation",
        0, 0, cash_modification, operation, transaction_time)
        alert = "Money withdrawn successfully!"


    return redirect(url_for(".index", alert=alert))





@app.route("/change_password", methods=["POST"])
@login_required
def change_password():
    """Allows the user to set a new password"""

    user_id = session["user_id"]

    # Query database for username
    rows = db.execute("SELECT * FROM users WHERE id = ?", user_id)

    if not check_password_hash(rows[0]["hash"], request.form.get("old-password")):
        return apology("INCORRECT OLD PASSWORD")


    if request.form.get("new-password") == request.form.get("confirm-password"):
        new_password = request.form.get("new-password")
        hashish = generate_password_hash(new_password)

        db.execute("UPDATE users SET hash = ? WHERE id = ?", hashish, user_id)
        alert = "Password changed!"

    else:
        return apology("WON'T WORK")



    return redirect(url_for(".index", alert=alert))


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
