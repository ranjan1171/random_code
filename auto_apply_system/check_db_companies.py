import sqlite3
conn = sqlite3.connect('db/jobs.db')
cur = conn.cursor()

# Get distinct companies
companies = cur.execute("SELECT DISTINCT company FROM jobs").fetchall()
print("Companies in jobs table:", [c[0] for c in companies])

# Delete any containing ubiquiti or anduril case-insensitively
cur.execute("DELETE FROM jobs WHERE lower(company) LIKE '%ubiquiti%' OR lower(company) LIKE '%anduril%'")
cur.execute("DELETE FROM applications WHERE lower(application_url) LIKE '%ubiquiti%' OR lower(application_url) LIKE '%anduril%'")
conn.commit()

# Print top 15 jobs remaining
print("\nTop 15 jobs in DB now:")
jobs = cur.execute("SELECT title, company, location, url, score FROM jobs ORDER BY score DESC LIMIT 15").fetchall()
for idx, j in enumerate(jobs, 1):
    print(f"{idx:2d}. [{j[4]}%] {j[0]} @ {j[1]} ({j[2]})")

conn.close()
