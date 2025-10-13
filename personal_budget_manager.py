import json
import csv
import os
from datetime import datetime, date, timedelta
from collections import defaultdict, OrderedDict
import statistics
import textwrap

DATA_FILE = "data.json"
DATE_FORMAT = "%Y-%m-%d"


def now_str():
    return datetime.now().strftime(DATE_FORMAT)


def ensure_data_file():
    if not os.path.exists(DATA_FILE):
        base = {
            "entries": [],  # each entry: {id, type, date, amount, category, description, recurring: {interval_days, until}}
            "budgets": {},  # key: "YYYY-MM" -> {category: amount}
            "next_id": 1
        }
        with open(DATA_FILE, "w") as f:
            json.dump(base, f, indent=2)


def load_data():
    ensure_data_file()
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def format_currency(amount):
    return f"${amount:.2f}"


def input_date(prompt="Date (YYYY-MM-DD) [today]: "):
    s = input(prompt).strip()
    if s == "":
        return date.today().strftime(DATE_FORMAT)
    try:
        d = datetime.strptime(s, DATE_FORMAT)
        return d.strftime(DATE_FORMAT)
    except Exception:
        print("Invalid date format. Use YYYY-MM-DD.")
        return input_date(prompt)


def input_float(prompt, allow_negative=False):
    s = input(prompt).strip()
    try:
        val = float(s)
        if not allow_negative and val < 0:
            print("Value cannot be negative.")
            return input_float(prompt, allow_negative)
        return val
    except Exception:
        print("Please enter a valid number.")
        return input_float(prompt, allow_negative)


def add_entry(data, etype=None, mock=False):
    """
    etype: "expense" or "income" or None -> ask
    mock: if True, use randomized/mock values for quick demo
    """
    if mock:
        # quick mock entry
        import random
        types = ["expense", "income"]
        etype = etype or random.choice(types)
        amount = round(random.uniform(5, 200), 2)
        category = random.choice(["Food", "Transport", "Bills", "Salary", "Shopping", "Other"])
        d = (date.today() - timedelta(days=random.randint(0, 30))).strftime(DATE_FORMAT)
        desc = "Mock entry"
        recurring = None
    else:
        if etype not in ("expense", "income"):
            etype = input("Type (expense/income): ").strip().lower()
            if etype not in ("expense", "income"):
                print("Invalid type.")
                return
        d = input_date()
        amount = input_float("Amount: ")
        category = input("Category: ").strip() or "Other"
        desc = input("Description (optional): ").strip()
        rec = input("Recurring? Enter interval in days (e.g., 30) or leave blank: ").strip()
        if rec:
            try:
                interval = int(rec)
                until = input("Until date (YYYY-MM-DD) or leave blank: ").strip()
                if until == "":
                    until = None
                else:
                    # validate
                    datetime.strptime(until, DATE_FORMAT)
                recurring = {"interval_days": interval, "until": until}
            except Exception:
                print("Invalid recurring input. Skipping recurring.")
                recurring = None
        else:
            recurring = None

    entry = {
        "id": data.get("next_id", 1),
        "type": etype,
        "date": d,
        "amount": amount,
        "category": category,
        "description": desc,
    }
    if not mock and recurring:
        entry["recurring"] = recurring
    data["entries"].append(entry)
    data["next_id"] = entry["id"] + 1
    save_data(data)
    print("Added:", entry_summary(entry))


def entry_summary(e):
    return f"[{e['id']}] {e['date']} {e['type']} {format_currency(e['amount'])} ({e.get('category','')}) {e.get('description','')}"


def list_entries(data, limit=50):
    entries = sorted(data["entries"], key=lambda x: x["date"], reverse=True)
    if not entries:
        print("No entries found.")
        return
    for e in entries[:limit]:
        print(entry_summary(e))


def delete_entry(data):
    list_entries(data, limit=200)
    try:
        eid = int(input("Enter id to delete: ").strip())
    except Exception:
        print("Invalid id.")
        return
    new = [e for e in data["entries"] if e["id"] != eid]
    if len(new) == len(data["entries"]):
        print("ID not found.")
    else:
        data["entries"] = new
        save_data(data)
        print("Deleted entry", eid)


def edit_entry(data):
    list_entries(data, limit=200)
    try:
        eid = int(input("Enter id to edit: ").strip())
    except Exception:
        print("Invalid id.")
        return
    for e in data["entries"]:
        if e["id"] == eid:
            print("Leave blank to keep current.")
            d = input_date(f"Date [{e['date']}]: ") or e["date"]
            amt = input(f"Amount [{e['amount']}]: ").strip()
            if amt == "":
                amount = e["amount"]
            else:
                try:
                    amount = float(amt)
                except:
                    print("Invalid amount.")
                    return
            cat = input(f"Category [{e.get('category','')}]: ").strip() or e.get("category", "")
            desc = input(f"Description [{e.get('description','')}]: ").strip() or e.get("description", "")
            e.update({"date": d, "amount": amount, "category": cat, "description": desc})
            save_data(data)
            print("Updated:", entry_summary(e))
            return
    print("ID not found.")


def apply_recurring_entries(data):
    """Populate recurring entries up to today if missing."""
    today = date.today()
    changed = False
    # collect recurring prototypes
    recs = [e for e in data["entries"] if e.get("recurring")]
    for prototype in recs:
        interval = prototype["recurring"]["interval_days"]
        until = prototype["recurring"].get("until")
        start = datetime.strptime(prototype["date"], DATE_FORMAT).date()
        last = start
        # find latest existing with same prototype id? We'll generate by comparing fields
        while True:
            next_date = last + timedelta(days=interval)
            if next_date > today:
                break
            if until:
                until_d = datetime.strptime(until, DATE_FORMAT).date()
                if next_date > until_d:
                    break
            # check if an entry exists with same date, amount, category, description
            exists = any(
                e["date"] == next_date.strftime(DATE_FORMAT)
                and abs(e["amount"] - prototype["amount"]) < 1e-6
                and e.get("category") == prototype.get("category")
                and e.get("description") == prototype.get("description")
                for e in data["entries"]
            )
            if not exists:
                # create new
                new = dict(prototype)
                new["id"] = data.get("next_id", 1)
                new["date"] = next_date.strftime(DATE_FORMAT)
                # do not copy recurring definition for generated entries to avoid infinite loop
                new.pop("recurring", None)
                data["entries"].append(new)
                data["next_id"] = new["id"] + 1
                changed = True
            last = next_date
    if changed:
        save_data(data)
        print("Applied recurring entries up to today.")


def set_budget_for_month(data):
    y = input("Year (YYYY) [current]: ").strip() or str(date.today().year)
    m = input("Month (1-12) [current]: ").strip() or str(date.today().month)
    try:
        ym = f"{int(y):04d}-{int(m):02d}"
    except:
        print("Invalid year/month.")
        return
    print("Enter budgets per category. Leave blank to stop.")
    budgets = {}
    while True:
        cat = input("Category (or blank to finish): ").strip()
        if not cat:
            break
        amt_s = input_float("Budget amount: ")
        budgets[cat] = amt_s
    data.setdefault("budgets", {})
    data["budgets"][ym] = budgets
    save_data(data)
    print("Saved budgets for", ym)


def get_entries_between(data, start_date, end_date):
    sd = datetime.strptime(start_date, DATE_FORMAT).date()
    ed = datetime.strptime(end_date, DATE_FORMAT).date()
    return [e for e in data["entries"] if sd <= datetime.strptime(e["date"], DATE_FORMAT).date() <= ed]


def monthly_summary(data, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    ym = f"{int(year):04d}-{int(month):02d}"
    start = date(int(year), int(month), 1)
    # compute end as first day next month minus one day
    if month == 12:
        end = date(int(year) + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(int(year), int(month) + 1, 1) - timedelta(days=1)
    entries = get_entries_between(data, start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT))
    income = sum(e["amount"] for e in entries if e["type"] == "income")
    expense = sum(e["amount"] for e in entries if e["type"] == "expense")
    by_cat = defaultdict(float)
    for e in entries:
        by_cat[e.get("category", "Uncategorized")] += e["amount"] if e["type"] == "expense" else -e["amount"]
    print("\n" + "=" * 40)
    print(f"Summary for {ym}")
    print("=" * 40)
    print(f"Income: {format_currency(income)}")
    print(f"Expense: {format_currency(expense)}")
    print(f"Net: {format_currency(income - expense)}\n")
    print("By Category (expenses positive):")
    for cat, amt in sorted(by_cat.items(), key=lambda x: -abs(x[1])):
        print(f"  {cat:<15} {format_currency(amt if amt >= 0 else -amt)}")
    # budgets
    budgets = data.get("budgets", {}).get(ym, {})
    if budgets:
        print("\nBudgets:")
        for cat, b in budgets.items():
            spent = sum(e["amount"] for e in entries if e.get("category") == cat and e["type"] == "expense")
            print(f"  {cat:<15} Budget {format_currency(b):<10} Spent {format_currency(spent):<10} Remaining {format_currency(b - spent)}")
    print("=" * 40 + "\n")


def yearly_overview(data, year=None):
    if year is None:
        year = date.today().year
    print(f"\nYearly overview for {year}")
    months = []
    for m in range(1, 13):
        start = date(int(year), m, 1)
        if m == 12:
            end = date(int(year) + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(int(year), m + 1, 1) - timedelta(days=1)
        entries = get_entries_between(data, start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT))
        income = sum(e["amount"] for e in entries if e["type"] == "income")
        expense = sum(e["amount"] for e in entries if e["type"] == "expense")
        months.append((m, income, expense))
    print("Month | Income     | Expense    | Net")
    print("---------------------------------------")
    for m, inc, exp in months:
        print(f"{m:2d}    | {format_currency(inc):10} | {format_currency(exp):10} | {format_currency(inc - exp)}")
    total_inc = sum(inc for _, inc, _ in months)
    total_exp = sum(exp for _, _, exp in months)
    print("---------------------------------------")
    print(f"Total | {format_currency(total_inc):10} | {format_currency(total_exp):10} | {format_currency(total_inc - total_exp)}\n")


def export_csv(data, filename="export.csv"):
    fields = ["id", "type", "date", "amount", "category", "description"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for e in data["entries"]:
            row = {k: e.get(k, "") for k in fields}
            writer.writerow(row)
    print("Exported to", filename)


def import_csv(data, filename):
    if not os.path.exists(filename):
        print("File not found.")
        return
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            try:
                entry = {
                    "id": data.get("next_id", 1),
                    "type": row["type"],
                    "date": row["date"],
                    "amount": float(row["amount"]),
                    "category": row.get("category", "Other"),
                    "description": row.get("description", "")
                }
                data["entries"].append(entry)
                data["next_id"] = entry["id"] + 1
                count += 1
            except Exception as ex:
                print("Skipping row due to error:", ex)
        save_data(data)
        print(f"Imported {count} rows.")


def stats_top_categories(data, n=5):
    by_cat = defaultdict(float)
    for e in data["entries"]:
        if e["type"] == "expense":
            by_cat[e.get("category", "Uncategorized")] += e["amount"]
    top = sorted(by_cat.items(), key=lambda x: -x[1])[:n]
    print("\nTop categories by spending:")
    for cat, amt in top:
        print(f"  {cat:<15} {format_currency(amt)}")
    print()


def search_entries(data, q):
    res = [e for e in data["entries"] if q.lower() in e.get("description", "").lower() or q.lower() in e.get("category","").lower()]
    if not res:
        print("No results.")
        return
    for e in res:
        print(entry_summary(e))


def pretty_menu():
    print(textwrap.dedent("""
    ================= Personal Budget Manager =================
    1) Add expense
    2) Add income
    3) Add mock entry (quick demo)
    4) List recent entries
    5) Edit entry
    6) Delete entry
    7) Apply recurring entries
    8) Set monthly budgets
    9) Monthly summary
    10) Yearly overview
    11) Top categories
    12) Export CSV
    13) Import CSV
    14) Search
    15) Help & About
    0) Exit
    ===========================================================
    """))


def help_text():
    print(textwrap.dedent("""
    Personal Budget Manager
    - Data stored in data.json in the same folder.
    - CSV import expects columns: type,date,amount,category,description
    - Use 'Add mock entry' for quick demo data.
    - Recurring entries: when adding an entry you can specify interval in days and until date.
    """))


def main_loop():
    ensure_data_file()
    data = load_data()
    while True:
        pretty_menu()
        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_entry(data, etype="expense")
        elif choice == "2":
            add_entry(data, etype="income")
        elif choice == "3":
            add_entry(data, etype=None, mock=True)
        elif choice == "4":
            list_entries(data, limit=200)
        elif choice == "5":
            edit_entry(data)
        elif choice == "6":
            delete_entry(data)
        elif choice == "7":
            apply_recurring_entries(data)
        elif choice == "8":
            set_budget_for_month(data)
        elif choice == "9":
            y = input("Year (YYYY) [current]: ").strip()
            m = input("Month (1-12) [current]: ").strip()
            try:
                yval = int(y) if y else None
                mval = int(m) if m else None
            except:
                print("Invalid year/month.")
                continue
            monthly_summary(data, year=yval, month=mval)
        elif choice == "10":
            y = input("Year (YYYY) [current]: ").strip()
            yval = int(y) if y else None
            yearly_overview(data, year=yval)
        elif choice == "11":
            stats_top_categories(data)
        elif choice == "12":
            fn = input("Filename [export.csv]: ").strip() or "export.csv"
            export_csv(data, fn)
        elif choice == "13":
            fn = input("Filename to import from: ").strip()
            import_csv(data, fn)
        elif choice == "14":
            q = input("Search query (category or part of description): ").strip()
            search_entries(data, q)
        elif choice == "15":
            help_text()
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main_loop()
